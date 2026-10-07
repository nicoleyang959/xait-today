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
  const LANGUAGE_KEY = "xait-today-language";
  const ORIGINAL_KEY = "xait-today-original-content";
  let language = "zh";
  let originalContent = false;
  let languageData = { ui: Object.create(null), content: Object.create(null) };
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

  const ownEntry = (catalog, source) => Object.prototype.hasOwnProperty.call(catalog, source) ? catalog[source] : null;
  const catalogEntry = (catalog, source) => ownEntry(catalog, source) || ownEntry(catalog, source.trim());
  const uiText = (source) => {
    const entry = ownEntry(languageData.ui, source);
    return entry && typeof entry[language] === "string" ? entry[language] : source;
  };
  const sidebarLabel = () => {
    const sidebar = document.getElementById("sidebar");
    const toggle = document.getElementById("sidebar-toggle") || document.getElementById("sidebarToggle");
    if (!sidebar || !toggle) return;
    const label = uiText(sidebar.classList.contains("collapsed") ? "展开历史栏" : "收起历史栏");
    toggle.setAttribute("aria-label", label);
    toggle.setAttribute("title", label);
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
    sidebar.inert = collapsed;
    sidebar.setAttribute("aria-hidden", String(collapsed));
    document.body.classList.toggle("sidebar-collapsed", collapsed);
    toggle.textContent = collapsed ? "›" : "‹";
    toggle.setAttribute("aria-expanded", String(!collapsed));
    sidebarLabel();
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

  // Translation is an inert, build-time catalog. Only original text nodes and
  // descriptive attributes are changed: links, numbers, code and source data stay intact.
  const payload = document.getElementById("xait-language-data");
  if (!payload || payload.tagName !== "TEMPLATE") return;
  try {
    const parsed = JSON.parse(payload.content.textContent);
    if (!parsed || parsed.schemaVersion !== 1 || !parsed.ui || !parsed.content) return;
    const cleanMap = (candidate) => {
      const result = Object.create(null);
      Object.entries(candidate).forEach(([source, entry]) => {
        if (entry && typeof entry === "object") {
          const translated = Object.create(null);
          ["zh", "en"].forEach((locale) => {
            if (typeof entry[locale] === "string" && entry[locale]) translated[locale] = entry[locale];
          });
          if (Object.keys(translated).length) result[source] = translated;
        }
      });
      return result;
    };
    languageData = { ui: cleanMap(parsed.ui), content: cleanMap(parsed.content) };
  } catch (_) {
    // A malformed or absent catalog never prevents access to the original briefing.
    return;
  }

  const ignoredSelector = "script, style, template, code, pre, [data-no-i18n], #language-status";
  const metadataSelector = [
    ".meta", ".tagline", ".issue-header", ".card-header", ".site-footer",
    ".sidebar", ".collection-status", ".brief-meta", ".brief-reason", ".brief-policy",
    ".brief-empty", ".brief-related summary", ".link-meta", ".wechat-meta", ".wechat-badge",
    ".wechat-state", ".wechat-origin", ".wechat-overview", ".wechat-item-badge", ".wechat-item-copy > span", ".social-meta", ".social-heat", ".social-rank-meta", ".social-rank-heat", ".social-rank-note", ".social-rank-date", ".social-rank-origin", ".social-rank-overview",
    ".social-status", ".social-origin", ".social-overview", ".social-origin-details summary",
    "#source-health", ".wechat-empty", ".social-empty", ".reading-nav", ".section h2",
    ".data-table th", ".theme-switcher", ".original-content-toggle", ".translation-notice"
  ].join(",");
  const textRecords = [];
  const walker = document.createTreeWalker(document.documentElement, NodeFilter.SHOW_TEXT);
  let textNode;
  while ((textNode = walker.nextNode())) {
    const parent = textNode.parentElement;
    if (!parent || parent.closest(ignoredSelector) || !textNode.nodeValue.trim()) continue;
    textRecords.push({ node: textNode, original: textNode.nodeValue, metadata: parent.tagName === "TITLE" || Boolean(parent.closest(metadataSelector)), heat: Boolean(parent.closest(".social-heat, .social-rank-heat")) });
  }
  const attributeRecords = [];
  document.querySelectorAll("[title], [aria-label], [data-label], meta[name='description'], meta[property='og:title'], meta[property='og:description']").forEach((element) => {
    if (element.closest("script, style, template, code, pre") || element.id === "sidebar-toggle" || element.id === "sidebarToggle") return;
    const attributes = element.tagName === "META" ? ["content"] : ["title", "aria-label", "data-label"];
    attributes.forEach((attribute) => {
      if (element.hasAttribute(attribute)) attributeRecords.push({ element, attribute, original: element.getAttribute(attribute) });
    });
  });

  const translateMetadata = (source, heat = false) => {
    if (language !== "en") return source;
    const exact = ownEntry(languageData.ui, source);
    if (exact && exact.en) return exact.en;
    let result = source;
    // These anchored formats describe UI metadata, never news prose or identifiers.
    const replacements = [
      [/^xAIT 今日( · \d{4}-\d{2}-\d{2})?$/, (_, suffix = "") => `xAIT Today${suffix}`],
      [/^今日 (\d+) 篇$/, (_, count) => `${count} article${count === "1" ? "" : "s"} today`],
      [/^相关报道（(\d+)）$/, (_, count) => `Related coverage (${count})`],
      [/^（北京时间） · (模型|产品|研究|教程|行业|开源|综合)$/, (_, category) => ` (China Standard Time, UTC+08:00) · ${uiText(category)}`],
      [/^采集于 ([^·]+?)(?: · (今日|最近))?$/, (_, date, badge) => `Collected on ${date}${badge ? ` · ${uiText(badge)}` : ""}`],
      [/^沿用 ([\d-]+)$/, (_, date) => `Previous snapshot from ${date}`],
      [/^公开快照生成于 (.+)$/, (_, date) => `Public snapshot generated at ${date}`],
      [/^(.+)每日推文$/, (_, name) => `${name} daily posts`],
      [/^今日日报未检出，展示来源最近一期（([\d-]+)）$/, (_, date) => `No daily issue found today; showing the latest source issue (${date})`],
      [/^(.+) 至 (.+)（北京时间；含起点，不含终点）$/, (_, start, end) => `${start} to ${end} (China Standard Time, UTC+08:00; start inclusive, end exclusive)`],
      [/^入选依据：AI 相关；来源记录时间在本期窗口内；采集成功。(?: 已按相同公开链接、明确原文链接或事件标识合并 (\d+) 条记录。)?$/, (_, count) => `Selection basis: AI-related; source-recorded publication time is within this issue's window; successfully collected.${count ? ` ${count} records merged using the same public URL, explicit original URL or event identifier.` : ""}`],
      [/^仅跟踪 APPSO、数字生命卡兹克、智东西、花叔；仅公开列表元数据，不使用后台阅读量。采集于 (.+)；相对时间以该采集时刻为准。$/, (_, timestamp) => `Tracks only APPSO, 数字生命卡兹克, 智东西 and 花叔; public-list metadata only, with no private readership metrics. Collected at ${timestamp}; relative times refer to that collection time.`],
      [/^仅跟踪 APPSO、数字生命卡兹克、智东西、花叔；按发布时间列出，不使用无法公开核验的后台阅读量。采集于 (.+)。$/, (_, date) => `Tracks only APPSO, 数字生命卡兹克, 智东西 and 花叔; listed by publication time, without private readership metrics that cannot be publicly verified. Collected on ${date}.`]
    ];
    for (const [pattern, replacement] of replacements) {
      if (pattern.test(result)) return result.replace(pattern, replacement);
    }
    // Metadata may concatenate several independently translatable labels.
    // Exact dictionary phrases are replaced longest-first to prevent partial matches.
    const phrases = Object.entries(languageData.ui)
      .filter(([text, entry]) => /[\u3400-\u9fff]/u.test(text) && text.length >= 4 && entry.en && entry.en !== text)
      .sort(([left], [right]) => right.length - left.length);
    phrases.forEach(([text, entry]) => { result = result.split(text).join(entry.en); });
    result = result
      .replace(/成功 (\d+)/g, "Success $1")
      .replace(/无新增 (\d+)/g, "No new items $1")
      .replace(/不可用 (\d+)/g, "Unavailable $1")
      .replace(/沿用旧快照 (\d+)/g, "Previous snapshot $1")
      .replace(/未运行 (\d+)/g, "Not run $1")
      .replace(/今日日报未检出，展示来源最近一期（([\d-]+)）/g, (_, date) => `No daily issue found today; showing the latest source issue (${date})`)
      .replace(/(^| · )(昨天|前天|刚刚)(?=$| · )/g, (_, separator, label) => separator + uiText(label))
      .replace(/(Shown at collection: )(昨天|前天|刚刚)/g, (_, prefix, label) => prefix + uiText(label))
      .replace(/：正常(?= · |$)/g, ": Available")
      .replace(/(\d+)\s*小时前/g, (_, count) => `${count} hour${count === "1" ? "" : "s"} ago`)
      .replace(/(\d+)\s*分钟前/g, (_, count) => `${count} minute${count === "1" ? "" : "s"} ago`)
      .replace(/(\d+)\s*天前/g, (_, count) => `${count} day${count === "1" ? "" : "s"} ago`)
      .replace(/(\d+) 条/g, "$1 items")
      .replace(/（北京时间）/g, " (China Standard Time, UTC+08:00)")
      .replace(/（快照）/g, " (snapshot)")
      .replace(/（未注明核验方式）/g, " (verification method not specified)")
      .replace(/相关度 (?=[\d.,])/g, "Relevance ")
      .replace(/采集 (?=\d{4}-)/g, "Collected at ")
      .replace(/发布 (?=\d{4}-)/g, "Published ")
      .replace(/条(?=\s*·|$)/g, "items");
    if (heat) {
      result = result
        .replace(/([\d.,]+)万(?=热度|观看|赞|评论|积分)/g, "$1 ×10k ")
        .replace(/([\d.,]+)亿(?=热度|观看|赞|评论|积分)/g, "$1 ×100m ")
        .replace(/([\d.,]+)(?=热度|观看|赞|评论|积分)/g, "$1 ")
        .replace(/热度/g, "engagement")
        .replace(/观看/g, "views")
        .replace(/赞/g, "likes")
        .replace(/评论/g, "comments")
        .replace(/积分/g, "points");
    } else {
      result = result.replace(/(\d+) 评论(?=$| · )/g, "$1 comments");
    }
    return result;
  };

  const translationFor = (original, metadata, heat = false) => {
    const source = original.trim();
    const ui = catalogEntry(languageData.ui, original);
    const content = catalogEntry(languageData.content, original);
    let translated = source;
    if (ui) translated = ui[language] ? ui[language].trim() : source;
    else if (content && !originalContent) translated = content[language] ? content[language].trim() : source;
    else if (metadata) translated = translateMetadata(source, heat);
    return original.slice(0, original.indexOf(source)) + translated + original.slice(original.indexOf(source) + source.length);
  };

  const protectedNames = new Set(["APPSO", "数字生命卡兹克", "智东西", "花叔", "Hacker News", "GitHub", "Reddit", "YouTube", "Techmeme", "Bluesky", "StockTwits", "Product Hunt", "Y Combinator", "arXiv", "aihot"]);
  const requiresTranslation = (source) => {
    const text = source.trim();
    if (protectedNames.has(text) || /^https?:\/\//.test(text) || /^[\w.-]+\/[\w.-]+$/.test(text) || /^\$[A-Za-z0-9._-]+\s+https?:\/\/\S+$/.test(text)) return false;
    if (language === "en") return /[\u3400-\u9fff]/u.test(text);
    return !/[\u3400-\u9fff]/u.test(text) && (text.match(/[A-Za-z]{2,}/g) || []).length > 1 && text.length > 12;
  };
  const untranslatedIn = (element) => textRecords.some((record) => {
    if (record.metadata || !element.contains(record.node) || !requiresTranslation(record.original)) return false;
    if (catalogEntry(languageData.ui, record.original)) return false;
    const entry = catalogEntry(languageData.content, record.original);
    return !entry || !entry[language];
  });
  const fallbackRecords = [];
  const appendFallback = (element, section) => {
    const badge = document.createElement("span");
    badge.className = "translation-unavailable" + (section ? " translation-section-notice" : "");
    badge.hidden = true;
    if (section) {
      const heading = element.querySelector("h2");
      if (heading) heading.insertAdjacentElement("afterend", badge);
      else element.appendChild(badge);
    } else element.appendChild(badge);
    fallbackRecords.push({ element, badge, section });
  };
  document.querySelectorAll(".brief-event, .wechat-copy, .wechat-item-copy, .social-copy, .social-rank-copy, .link-item, .section-table .data-table tbody tr td:last-child").forEach((element) => appendFallback(element, false));
  document.querySelectorAll(".section-blocks:not(#source-health)").forEach((element) => appendFallback(element, true));

  const updateLanguage = (selected, updateUrl = false) => {
    language = selected === "en" ? "en" : "zh";
    document.documentElement.lang = language === "en" ? "en" : "zh-CN";
    textRecords.forEach((record) => { record.node.nodeValue = translationFor(record.original, record.metadata, record.heat); });
    attributeRecords.forEach((record) => { record.element.setAttribute(record.attribute, translationFor(record.original, true)); });
    document.querySelectorAll(".language-btn").forEach((button) => {
      const active = button.dataset.language === language;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    const originalToggle = document.getElementById("original-content-toggle");
    if (originalToggle) {
      originalToggle.setAttribute("aria-pressed", String(originalContent));
      originalToggle.textContent = uiText(originalContent ? "返回译文" : "查看原文");
      originalToggle.setAttribute("title", uiText("仅切换新闻内容，界面语言保持不变"));
    }
    let missing = 0;
    fallbackRecords.forEach(({ element, badge, section }) => {
      const show = !originalContent && untranslatedIn(element);
      badge.hidden = !show;
      badge.textContent = uiText(section ? "部分内容保留原文 · 暂无译文" : "原文 · 暂无译文");
      if (show) missing += 1;
    });
    const notice = document.getElementById("translation-notice");
    if (notice) notice.textContent = uiText(originalContent ? "当前显示新闻原文；界面语言保持不变，来源链接始终保留。" : "译文由 AI 辅助预生成，仅供阅读参考；原文及来源链接始终保留。");
    const status = document.getElementById("language-status");
    if (status) status.textContent = language === "en" ? `English selected.${originalContent ? " Original news content is shown." : missing ? ` ${missing} items or sections retain their original text where a translation is unavailable.` : ""}` : `已切换为中文。${originalContent ? "当前显示新闻原文。" : missing ? `${missing} 条内容或栏目暂无译文，保留原文。` : ""}`;
    sidebarLabel();
    safeWrite(LANGUAGE_KEY, language);
    safeWrite(ORIGINAL_KEY, originalContent ? "1" : "0");
    if (updateUrl) {
      try {
        const url = new URL(window.location.href);
        url.searchParams.set("lang", language);
        window.history.replaceState(null, "", url);
      } catch (_) {
        // File previews and restricted browsers may not permit history updates.
      }
    }
  };

  document.querySelectorAll(".language-btn").forEach((button) => {
    button.addEventListener("click", () => updateLanguage(button.dataset.language, true));
  });
  const originalToggle = document.getElementById("original-content-toggle");
  if (originalToggle) originalToggle.addEventListener("click", () => {
    originalContent = !originalContent;
    updateLanguage(language);
  });
  let requestedLanguage = null;
  try { requestedLanguage = new URL(window.location.href).searchParams.get("lang"); } catch (_) { /* Keep the saved preference. */ }
  originalContent = safeRead(ORIGINAL_KEY) === "1";
  const initialLanguage = requestedLanguage === "zh" || requestedLanguage === "en" ? requestedLanguage : safeRead(LANGUAGE_KEY);
  updateLanguage(initialLanguage);
  const legacySidebarToggle = document.getElementById("sidebarToggle");
  if (legacySidebarToggle) legacySidebarToggle.addEventListener("click", () => {
    // Legacy local archives own their inline toggle; relabel after that handler
    // without attaching a second collapse/expand action.
    Promise.resolve().then(sidebarLabel);
  });
})();
