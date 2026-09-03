(() => {
  "use strict";

  const THEMES = new Set([
    "theme-terminal",
    "theme-cyberpunk",
    "theme-swiss",
    "theme-editorial",
    "theme-consulting",
    "theme-minimal",
    "theme-paper"
  ]);
  const THEME_KEY = "xait-today-theme";
  const SIDEBAR_KEY = "xait-today-sidebar";
  const PREVIOUS_THEME_KEY = String.fromCharCode(
    110, 105, 99, 111, 108, 101, 45, 98, 114, 105, 101, 102, 105, 110, 103,
    45, 116, 104, 101, 109, 101
  );
  const PREVIOUS_SIDEBAR_KEY = "xait-sidebar-collapsed";
  const PREVIOUS_THEMES = new Map([
    ["light", "theme-editorial"],
    ["theme-midnight", "theme-minimal"],
    ["theme-hud", "theme-swiss"]
  ]);

  const safeRead = (key) => {
    try {
      return window.localStorage.getItem(key);
    } catch (_) {
      return null;
    }
  };

  const safeWrite = (key, value) => {
    try {
      window.localStorage.setItem(key, value);
    } catch (_) {
      // Storage can be disabled without affecting reading or navigation.
    }
  };

  const safeRemove = (key) => {
    try {
      window.localStorage.removeItem(key);
    } catch (_) {
      // A failed cleanup does not affect the migrated preference.
    }
  };

  const normalizeTheme = (theme) => {
    const migrated = PREVIOUS_THEMES.get(theme) || theme;
    return THEMES.has(migrated) ? migrated : "theme-terminal";
  };

  const applyTheme = (theme) => {
    const selected = normalizeTheme(theme);
    document.body.classList.remove(...THEMES);
    document.body.classList.add(selected);
    document.querySelectorAll(".theme-btn").forEach((button) => {
      const active = button.dataset.theme === selected;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    safeWrite(THEME_KEY, selected);
  };

  const applySidebar = (collapsed) => {
    const sidebar = document.getElementById("sidebar");
    const toggle = document.getElementById("sidebar-toggle");
    if (!sidebar || !toggle) return;
    sidebar.classList.toggle("collapsed", collapsed);
    document.body.classList.toggle("sidebar-collapsed", collapsed);
    toggle.textContent = collapsed ? "›" : "‹";
    toggle.setAttribute("aria-expanded", String(!collapsed));
    toggle.setAttribute("aria-label", collapsed ? "展开历史栏" : "收起历史栏");
    toggle.setAttribute("title", collapsed ? "展开历史栏" : "收起历史栏");
    safeWrite(SIDEBAR_KEY, collapsed ? "collapsed" : "expanded");
  };

  document.querySelectorAll(".theme-btn").forEach((button) => {
    button.addEventListener("click", () => applyTheme(button.dataset.theme));
  });

  const sidebarToggle = document.getElementById("sidebar-toggle");
  if (sidebarToggle) {
    sidebarToggle.addEventListener("click", () => {
      const sidebar = document.getElementById("sidebar");
      applySidebar(Boolean(sidebar && !sidebar.classList.contains("collapsed")));
    });
  }

  let savedTheme = safeRead(THEME_KEY);
  if (savedTheme === null) {
    const previousTheme = safeRead(PREVIOUS_THEME_KEY);
    if (previousTheme !== null) {
      savedTheme = normalizeTheme(previousTheme);
      safeWrite(THEME_KEY, savedTheme);
      safeRemove(PREVIOUS_THEME_KEY);
    }
  }
  applyTheme(savedTheme);

  let savedSidebar = safeRead(SIDEBAR_KEY);
  if (savedSidebar === null) {
    const previousSidebar = safeRead(PREVIOUS_SIDEBAR_KEY);
    if (previousSidebar === "1" || previousSidebar === "0") {
      savedSidebar = previousSidebar === "1" ? "collapsed" : "expanded";
      safeWrite(SIDEBAR_KEY, savedSidebar);
      safeRemove(PREVIOUS_SIDEBAR_KEY);
    }
  }
  const compactFirstVisit = savedSidebar === null && window.matchMedia("(max-width: 840px)").matches;
  applySidebar(savedSidebar === "collapsed" || compactFirstVisit);
})();
