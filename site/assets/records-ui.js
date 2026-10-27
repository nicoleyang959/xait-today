/* Private library UI. It never supplies private content to the public builder. */
(function (root) {
  "use strict";
  const AUTH_PARAMS = ["code", "error", "error_code", "error_description", "access_token", "refresh_token", "provider_token", "provider_refresh_token", "token_type", "expires_in", "expires_at"];
  const STATES = ["to_research", "tried", "watching"];
  const COPY = {
    heading: ["我的项目", "My projects"], intro: ["把值得研究的项目留下来，笔记只对你的账号可见。", "Keep useful projects and your own private research notes."], back: ["返回日报", "Back to briefing"],
    unconfiguredHeading: ["云收藏尚未启用", "Cloud library is not configured"], unconfigured: ["站点尚未配置私人同步服务。你仍可正常阅读日报，配置完成后再登录收藏。", "Private sync is not configured on this site. The public briefing remains available."],
    login: ["用 GitHub 登录", "Sign in with GitHub"], loginHeading: ["你的私人项目库", "Your private project library"], loginMessage: ["登录后即可收藏项目、写笔记，并在自己的设备间同步。其他读者无法查看你的记录。", "Sign in to save projects and notes across your devices. Other readers cannot access your records."],
    privacy: ["收藏与笔记保存在本机和站点配置的 Supabase 服务中，不会写进公开日报或 GitHub 仓库。首次登录需要联网。", "Records are stored on this device and the site's Supabase service, never in public briefings or the GitHub repository. First sign-in requires a connection."],
    sync: ["立即同步", "Sync now"], signout: ["退出账号", "Sign out"], searchLabel: ["搜索项目", "Search projects"], searchPlaceholder: ["名称、链接或笔记", "Name, link or notes"], filterLabel: ["跟进状态", "Research status"],
    all: ["全部状态", "All statuses"], to_research: ["待研究", "To research"], tried: ["已体验", "Tried"], watching: ["重点关注", "Watching"], manualAdd: ["手动添加项目", "Add a project link"], projectName: ["项目名称", "Project name"], projectUrl: ["项目链接", "Project URL"],
    manualHelp: ["只保存你输入的链接，不访问目标网站或自动抓取内容。", "Only the link you enter is saved. The target site is not fetched."], saveProject: ["收藏项目", "Save project"], save: ["收藏", "Save"], saved: ["已收藏", "Saved"],
    exportJson: ["导出 JSON 备份", "Export JSON backup"], exportMarkdown: ["导出 Markdown", "Export Markdown"], importJson: ["导入 JSON 备份", "Import JSON backup"], backupLabel: ["项目备份", "Project backups"], chooseBackup: ["选择 JSON 备份", "Choose JSON backup"], savedList: ["已收藏项目", "Saved projects"],
    empty: ["还没有收藏项目。在日报里点击“收藏”，或手动添加一个项目链接。", "No projects saved yet. Save a project from the briefing, or add a link."], noMatches: ["没有匹配的项目。试试其他关键词，或选择全部状态。", "No matching projects. Try another search or choose all statuses."],
    editHeading: ["项目笔记", "Project notes"], notes: ["为什么值得关注？", "Why is this worth following?"], notesPlaceholder: ["记下用途、想试的功能，或你自己的判断。", "Record a use case, something to try, or your own assessment."], noteHelp: ["最多 5,000 字。笔记保留你输入的语言，不会自动翻译。", "Up to 5,000 characters. Your notes are kept in their original language, not translated."], saveNotes: ["保存笔记", "Save notes"], closeEditor: ["收起编辑", "Close editor"],
    pending: ["待同步", "Pending sync"], synced: ["已同步", "Synced"], error: ["同步失败", "Sync failed"], conflict: ["有冲突", "Conflict"], syncing: ["正在同步…", "Syncing…"], localSaved: ["项目已存本地。", "Project saved on this device."], notesSaved: ["笔记已存本地。", "Notes saved on this device."],
    cloudSaved: ["云端已确认，其他设备联网后会自动同步。", "Cloud confirmed. Your other devices will sync when connected."], offline: ["离线：记录会先保存在本机，联网后自动同步。", "Offline: records stay on this device and sync when connected."], signInAgain: ["需要重新登录同一账号后才能同步；本地记录仍然保留。", "Sign in to the same account again to sync. Local records are retained."],
    unavailable: ["同步服务暂不可用。本地记录仍保留，稍后可重试或导出备份。", "Sync is temporarily unavailable. Local records remain safe; retry later or export a backup."], storageError: ["浏览器未能保存记录。请检查站点存储权限或剩余空间；本次未显示保存成功。", "The browser could not save the record. Check site storage permissions or available space; this save was not confirmed."],
    invalidLink: ["请输入不含登录信息的公开 HTTP 或 HTTPS 链接。", "Enter a public HTTP or HTTPS link without embedded sign-in information."], invalidRecord: ["记录格式不正确，或超过长度限制。请检查名称、链接和笔记。", "Invalid record or a field is too long. Check the name, URL and notes."], quota: ["已达到项目数量或存储额度。本地草稿已保留，不会自动升级付费。", "A record or storage limit was reached. Local drafts are retained; no paid upgrade is started."],
    firstOnline: ["首次登录需要联网。请连接网络后重试；不会把匿名记录自动归入其他账号。", "First sign-in requires a connection. Connect and retry; anonymous records will not be assigned to another account."], foreign: ["此副本未获准连接原站的私人服务，请配置自己的云项目。日报阅读不受影响。", "This copy is not configured to use the original site's private service. Configure your own cloud project; reading is unaffected."],
    sdkMissing: ["收藏模块未能加载。请刷新重试；日报仍可阅读。", "The library module could not load. Refresh and retry; the briefing remains available."], loginFailed: ["登录未完成或已过期，请重试。不会显示或记录认证详情。", "Sign-in did not complete or expired. Please retry. Authentication details are not displayed or logged."],
    edit: ["写笔记", "Edit notes"], remove: ["移除", "Remove"], removeTitle: ["移除这个项目？", "Remove this project?"], removeMessage: ["云端确认后将清除项目正文和笔记。其他设备的旧编辑不能自动恢复它。", "After cloud confirmation, project content and notes will be cleared. Old edits on other devices cannot restore it automatically."], removed: ["移除操作已存本地。", "Removal saved on this device."],
    cancel: ["取消", "Cancel"], confirm: ["确认", "Confirm"], restoreTitle: ["重新收藏项目？", "Save this project again?"], restoreMessage: ["这个链接曾被移除。需要明确重新收藏，旧的离线编辑不会自动恢复它。", "This link was previously removed. Save it again explicitly; old offline edits will not restore it."], restore: ["重新收藏", "Save again"],
    discardTitle: ["有尚未保存的编辑", "Unsaved edits"], discardMessage: ["要放弃当前输入吗？你也可以取消，先保存笔记。", "Discard the current input? You can cancel and save the notes first."], discard: ["放弃编辑", "Discard edits"],
    conflictTitle: ["两台设备修改了同一个项目", "This project changed on another device"], conflictMessage: ["两份内容都已保留。选择保留哪一份，或把云端内容带回编辑框手动合并。", "Both versions are retained. Choose one, or return to the editor to merge them."], localVersion: ["本机草稿", "Local draft"], remoteVersion: ["云端版本", "Cloud version"], keepLocal: ["保留本机草稿", "Keep local draft"], keepRemote: ["采用云端版本", "Use cloud version"], merge: ["编辑合并", "Edit a merge"], resolve: ["处理冲突", "Resolve conflict"], deletedVersion: ["这个项目已在另一台设备上移除。", "This project was removed on another device."],
    signoutTitle: ["退出前处理待同步内容", "Before signing out"], signoutMessage: ["存在未同步记录或尚未保存的笔记。默认取消退出；请先同步、导出备份，或明确放弃本机待同步内容。", "You have pending records or unsaved notes. Cancel by default; sync, export a backup, or explicitly discard local pending content."], exportFirst: ["先导出备份", "Export backup first"], discardAndOut: ["放弃待同步内容并退出", "Discard pending content and sign out"], signoutDone: ["已退出，已清除此账号的本机缓存和会话。", "Signed out. This account's local cache and session were cleared."], signoutPartial: ["已退出并清除登录会话，但浏览器未能清除部分本机缓存。请在浏览器设置中清除此站点数据。", "Signed out and cleared the sign-in session, but some device cache could not be removed. Clear this site's data in browser settings."],
    importTitle: ["导入到当前账号？", "Import into this account?"], importMessage: ["备份将加入当前登录账号。相同链接不会静默覆盖笔记；差异会保留为冲突。", "The backup will be added to the signed-in account. Duplicate links will not silently overwrite notes; differences become conflicts."], imported: ["备份已加入本地队列，联网后同步。请检查可能的冲突。", "Backup added to the local queue. It will sync when connected; check for conflicts."], badBackup: ["备份无效或超过大小限制，未导入任何内容。请选择由项目库导出的 JSON 文件。", "Invalid or oversized backup. Nothing was imported. Choose a JSON backup exported by the library."], exported: ["备份已导出，请妥善保管其中的私人笔记。", "Backup exported. Keep its private notes secure."],
    allSynced: ["所有记录已同步", "All records synced"], draft: ["本地草稿", "Local draft"], draftState: ["有本地草稿，保存笔记后同步", "Local drafts; save the notes to sync"], source: ["发现来源", "Discovered in"], manual: ["手动添加", "Added manually"], account: ["当前账号", "Account"], projectCount: ["个项目", "projects"], displayed: ["显示", "Showing"], localOnly: ["本机保存", "Saved locally"], offlineAccount: ["离线账号", "Offline account"]
  };
  function readConfig(text) {
    const value = JSON.parse(text);
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("config");
    const allowed = ["enabled", "supabaseUrl", "publishableKey", "redirectUrl"];
    if (Object.keys(value).some((key) => !allowed.includes(key)) || allowed.some((key) => !(key in value))) throw new Error("config");
    if (typeof value.enabled !== "boolean" || allowed.slice(1).some((key) => typeof value[key] !== "string")) throw new Error("config");
    if (!value.enabled) {
      if (allowed.slice(1).some((key) => value[key] !== "")) throw new Error("config");
      return value;
    }
    const service = new URL(value.supabaseUrl);
    const redirect = new URL(value.redirectUrl);
    if (service.protocol !== "https:" || !/^[a-z0-9]{20}\.supabase\.co$/.test(service.hostname) || service.origin !== value.supabaseUrl || service.pathname !== "/" || !/^sb_publishable_[A-Za-z0-9_-]{16,256}$/.test(value.publishableKey)) throw new Error("config");
    if (redirect.protocol !== "https:" || redirect.username || redirect.password || redirect.search || redirect.hash || !redirect.pathname.endsWith("/")) throw new Error("config");
    return value;
  }
  function isAllowedRuntime(config, homeHref, locationHref, secure) {
    if (!config.enabled || !secure) return false;
    const home = new URL(homeHref, locationHref);
    const current = new URL(locationHref);
    const redirect = new URL(config.redirectUrl);
    return home.href === redirect.href && current.origin === redirect.origin && current.pathname.startsWith(redirect.pathname);
  }
  function safeReturnPath(value, baseHref) {
    try {
      const base = new URL(baseHref);
      const target = new URL(value, base);
      const fragment = new URLSearchParams(target.hash.slice(1));
      if (target.origin !== base.origin || !target.pathname.startsWith(base.pathname) || AUTH_PARAMS.some((key) => target.searchParams.has(key) || fragment.has(key))) return null;
      return target.pathname + target.search + target.hash;
    } catch (_) { return null; }
  }
  function errorKey(error) {
    const code = String(error && (error.code || error.name) || "").toLowerCase();
    if (/quota|limit/.test(code)) return "quota";
    if (/url|link/.test(code)) return "invalidLink";
    if (/storage|indexed|transaction|dataerror/.test(code)) return "storageError";
    if (/auth|session|sign.?in/.test(code)) return "signInAgain";
    if (/valid|record|backup|payload|length/.test(code)) return "invalidRecord";
    return "unavailable";
  }
  function cleanAuthLocation(href) {
    const url = new URL(href);
    const code = url.searchParams.get("code");
    const hasError = url.searchParams.has("error") || url.searchParams.has("error_code");
    let changed = false;
    AUTH_PARAMS.forEach((key) => { if (url.searchParams.has(key)) { changed = true; url.searchParams.delete(key); } });
    const fragment = new URLSearchParams(url.hash.slice(1));
    if (AUTH_PARAMS.some((key) => fragment.has(key))) { url.hash = ""; changed = true; }
    return { code, hasError, changed, clean: url.pathname + url.search + url.hash };
  }
  const exports = { readConfig, isAllowedRuntime, safeReturnPath, errorKey, cleanAuthLocation, AUTH_PARAMS: AUTH_PARAMS.slice() };
  if (typeof module !== "undefined" && module.exports) module.exports = exports;
  if (!root.document) return;

  const document = root.document;
  const $ = (id) => document.getElementById(id);
  const view = $("saved-projects");
  if (!view) return;
  const t = (key) => (COPY[key] || COPY.unavailable)[document.documentElement.lang.toLowerCase().startsWith("en") ? 1 : 0];
  let config = null, client = null, library = null, userId = null, userLabel = "", generation = 0;
  let records = [], syncing = false, syncPromise = null, onlineVerified = false, sessionBlocked = false;
  let editorBase = null, editorDirty = false, editorMerge = null, toastTimer = null, draftTimer = null, lastFocus = null, readingScroll = 0, returnHash = "";
  let subscription = null, pollTimer = null, storageKey = "", namespace = "", lastIdentityKey = "", intentKey = "";
  let gateReason = null;
  let feedbackKey = null, feedbackTone = "info", toastKey = null;
  let previousHash = root.location.hash === "#saved" ? "" : root.location.hash;
  const core = () => root.XaitRecordsCore;
  const ownRead = (store, key) => { try { return store.getItem(key); } catch (_) { return null; } };
  const ownWrite = (store, key, value) => { try { store.setItem(key, value); return true; } catch (_) { return false; } };
  const ownRemove = (store, key) => { try { store.removeItem(key); } catch (_) { /* Nothing is reported as saved. */ } };
  function localize() {
    if ($("saved-open")) $("saved-open").textContent = t("heading");
    view.querySelectorAll("[data-records-text]").forEach((node) => { node.textContent = t(node.dataset.recordsText); });
    view.querySelectorAll("[data-records-placeholder]").forEach((node) => { node.placeholder = t(node.dataset.recordsPlaceholder); });
    view.querySelectorAll("[data-records-aria]").forEach((node) => { node.setAttribute("aria-label", t(node.dataset.recordsAria)); });
    if (feedbackKey) feedback(feedbackKey, feedbackTone);
    if (toastKey) $("records-toast").textContent = t(toastKey);
    updateButtons();
    if (library) {
      $("records-account").textContent = t("account") + ": " + userLabel;
      renderList(); Promise.resolve(refresh()).catch(reportError);
    } else renderGate();
  }
  function feedback(key, tone = "info") {
    feedbackKey = key; feedbackTone = tone;
    const node = $("records-feedback");
    node.textContent = key ? t(key) : "";
    node.dataset.tone = tone;
  }
  function toast(key) {
    toastKey = key;
    const node = $("records-toast");
    node.textContent = t(key); node.hidden = false;
    root.clearTimeout(toastTimer);
    toastTimer = root.setTimeout(() => { node.hidden = true; }, 6000);
  }
  function node(tag, text, className) {
    const result = document.createElement(tag);
    if (text !== undefined) result.textContent = text;
    if (className) result.className = className;
    return result;
  }
  function button(key, action, className = "") {
    const result = node("button", t(key), "records-button " + className);
    result.type = "button";
    result.addEventListener("click", () => { Promise.resolve(action()).catch(reportError); });
    return result;
  }
  function reportError(error) { feedback(errorKey(error), "error"); }
  async function ask(titleKey, messageKey, choices, detail) {
    const dialog = $("records-dialog");
    if (!dialog || typeof dialog.showModal !== "function") return "cancel";
    if (dialog.open) return "cancel";
    $("records-dialog-title").textContent = t(titleKey);
    $("records-dialog-message").textContent = t(messageKey);
    const details = $("records-dialog-detail"); details.replaceChildren();
    if (detail) {
      for (const [heading, content] of detail) {
        const box = node("section", undefined, "records-conflict-version");
        box.append(node("h3", t(heading)), node("p", content)); details.append(box);
      }
    }
    const actions = $("records-dialog-actions"); actions.replaceChildren();
    choices.forEach(([value, key, danger]) => {
      const action = node("button", t(key), "records-button" + (danger ? " records-danger" : ""));
      action.type = "submit"; action.value = value;
      if (value === "cancel") action.autofocus = true;
      actions.append(action);
    });
    const focus = document.activeElement;
    return new Promise((resolve) => {
      const done = () => {
        dialog.removeEventListener("close", done);
        const value = dialog.returnValue || "cancel";
        if (focus && focus.isConnected) focus.focus();
        resolve(value);
      };
      dialog.returnValue = "cancel";
      dialog.addEventListener("close", done);
      dialog.showModal();
    });
  }
  function renderGate(reason) {
    if (reason !== undefined) gateReason = reason;
    const valid = config && config.enabled && !gateReason;
    $("records-workspace").hidden = true;
    $("records-gate").hidden = false;
    const heading = !config || !config.enabled ? "unconfiguredHeading" : "loginHeading";
    const message = gateReason || (!config || !config.enabled ? "unconfigured" : "loginMessage");
    $("records-gate-heading").textContent = t(heading);
    $("records-gate-message").textContent = t(message);
    $("records-login").hidden = !valid || !client;
    $("records-login").disabled = !valid || !client;
  }
  function lock() {
    root.clearTimeout(draftTimer);
    if (library && editorDirty && editorBase && library.saveEditorDraft) {
      // This write remains bound to the old account and does not contact the cloud.
      Promise.resolve(persistEditorDraft()).catch(() => {});
    }
    generation += 1;
    if (library) library.stop();
    library = null; userId = null; records = []; onlineVerified = false;
    syncing = false; syncPromise = null;
    editorBase = null; editorDirty = false; editorMerge = null;
    $("records-editor").hidden = true;
    $("records-list").replaceChildren();
    $("records-account").textContent = "";
    $("records-count").textContent = "";
    $("records-sync-state").textContent = "";
    $("records-search").value = "";
    $("records-filter").value = "all";
    $("records-manual-form").reset();
    $("records-add").open = false;
    $("records-edit-id").value = "";
    $("records-edit-status").value = "to_research";
    $("records-edit-notes").value = "";
    $("records-edit-title").value = "";
    if ($("records-dialog").open) $("records-dialog").close("cancel");
    renderGate(); updateButtons();
    return generation;
  }
  function rememberIdentity(id, label) { ownWrite(root.localStorage, lastIdentityKey, JSON.stringify({ id, label })); }
  function recalledIdentity() {
    try {
      const value = JSON.parse(ownRead(root.localStorage, lastIdentityKey) || "null");
      return value && typeof value.id === "string" && /^[0-9a-f-]{36}$/i.test(value.id) && typeof value.label === "string" ? value : null;
    } catch (_) { return null; }
  }
  function accountLabel(user) {
    const meta = user.user_metadata || {};
    return String(meta.user_name || meta.preferred_username || user.email || user.id).slice(0, 100);
  }
  function guardedTransport(epoch, id) {
    const base = core().createSupabaseTransport(client, id);
    const activeClient = client;
    async function check() {
      if (epoch !== generation || id !== userId || sessionBlocked || !root.navigator.onLine) throw Object.assign(new Error("session"), { code: "session_required" });
      const result = await activeClient.auth.getUser();
      if (epoch !== generation || id !== userId) throw Object.assign(new Error("session"), { code: "session_required" });
      if (result.error || !result.data || !result.data.user || result.data.user.id !== id) {
        onlineVerified = false;
        if (result.data && result.data.user && result.data.user.id !== id) {
          const changedUser = result.data.user;
          lock();
          root.setTimeout(() => { Promise.resolve(onSession({ user: changedUser })).catch(reportError); }, 0);
        }
        throw Object.assign(new Error("session"), { code: "session_required" });
      }
      onlineVerified = true;
    }
    return {
      async list(after) { await check(); return base.list(after); },
      async mutate(operation) { await check(); return base.mutate(operation); }
    };
  }
  async function activate(identity) {
    if (sessionBlocked || !identity || !identity.id || !core()) return;
    if (userId === identity.id && library) { userLabel = identity.label; return; }
    const epoch = lock();
    userId = identity.id; userLabel = identity.label;
    try {
      const store = await core().openStore(namespace, userId);
      if (epoch !== generation || userId !== identity.id) { if (store.close) store.close(); return; }
      const next = new (core().Library)({ store, transport: guardedTransport(epoch, userId), onChange: () => {
        if (epoch === generation) Promise.resolve(refresh()).catch(reportError);
      } });
      library = next;
      await next.init();
      if (epoch !== generation || library !== next) { next.stop(); return; }
      $("records-gate").hidden = true;
      gateReason = null;
      $("records-workspace").hidden = false;
      $("records-account").textContent = t("account") + ": " + userLabel;
      rememberIdentity(identity.id, identity.label);
      await refresh();
      if (root.navigator.onLine) await synchronize(); else feedback("offline");
    } catch (error) {
      if (epoch === generation) { lock(); renderGate("storageError"); reportError(error); }
    }
  }
  async function onSession(session) {
    if (sessionBlocked) return;
    if (session && session.user) {
      await activate({ id: session.user.id, label: accountLabel(session.user) });
      if (library) await restoreIntent();
    } else if (!root.navigator.onLine && recalledIdentity()) {
      await activate(recalledIdentity());
      feedback("signInAgain");
    } else {
      lock();
    }
  }
  function updateButtons() {
    document.querySelectorAll("[data-save-project]").forEach((action) => {
      let existing = null;
      try { if (core()) existing = records.find((record) => record.canonical_url === core().normalizeUrl(action.dataset.projectUrl)); } catch (_) { /* The source button remains unavailable. */ }
      const available = Boolean(config && config.enabled && client && core());
      action.disabled = !available;
      action.setAttribute("aria-pressed", String(Boolean(existing)));
      const label = action.querySelector("[data-save-label]");
      if (label) label.textContent = t(existing ? "saved" : "save");
      else action.textContent = t(existing ? "saved" : "save");
      action.title = t(available ? (existing ? "edit" : "saveProject") : "unconfigured");
    });
  }
  async function refresh() {
    if (!library) return;
    const current = library, epoch = generation;
    const result = await current.list();
    if (epoch !== generation || current !== library) return;
    records = result.filter((record) => !record.deleted_at || record.sync_state === "conflict");
    renderList(); updateButtons();
    const pending = await current.pendingCount();
    const drafts = current.editorDraftCount ? await current.editorDraftCount() : 0;
    if (epoch !== generation) return;
    $("records-sync-state").textContent = syncing ? t("syncing") : records.some((record) => record.sync_state === "conflict") ? t("conflict") : pending ? pending + " · " + t("pending") : drafts ? t("draftState") : t("allSynced");
  }
  function renderList() {
    if (!library) return;
    const query = $("records-search").value.trim().toLocaleLowerCase();
    const status = $("records-filter").value;
    const shown = records.filter((record) => (status === "all" || record.status === status) && [record.title, record.url, record.notes].join(" ").toLocaleLowerCase().includes(query));
    shown.sort((a, b) => String(b.updated_at || "").localeCompare(String(a.updated_at || "")) || String(a.id).localeCompare(String(b.id)));
    $("records-count").textContent = t("displayed") + " " + shown.length + " / " + records.length + " " + t("projectCount");
    $("records-empty").hidden = Boolean(shown.length);
    $("records-empty").textContent = t(records.length ? "noMatches" : "empty");
    const list = $("records-list"); list.replaceChildren();
    shown.forEach((record) => {
      const item = node("li", undefined, "records-item");
      item.dataset.recordId = record.id;
      const copy = node("div");
      const title = node("h3");
      let projectUrl = null;
      try { projectUrl = core().normalizeUrl(record.url); } catch (_) { /* Never render an unsafe server value as a link. */ }
      if (projectUrl) {
        const link = node("a", record.title || record.url); link.href = record.url; link.target = "_blank"; link.rel = "noopener noreferrer"; title.append(link);
      } else title.textContent = record.title || t("deletedVersion");
      copy.append(title, node("span", record.url || "", "records-item-url"));
      const meta = node("div", undefined, "records-item-meta");
      meta.append(node("span", t(STATES.includes(record.status) ? record.status : "to_research")), node("span", t(record.sync_state || "synced"), "records-item-sync"));
      if (record.has_editor_draft) meta.append(node("span", t("draft"), "records-item-sync"));
      if (record.source_issue_date && /^\d{4}-\d{2}-\d{2}$/.test(record.source_issue_date)) {
        const source = node("a", record.source_issue_date + (record.source_id ? " · " + record.source_id : ""));
        source.href = new URL("archive/" + record.source_issue_date + "/", config.redirectUrl).href;
        meta.append(source);
      } else meta.append(node("span", t("manual")));
      copy.append(meta);
      if (record.notes) copy.append(node("p", record.notes, "records-item-notes"));
      const actions = node("div", undefined, "records-item-actions");
      actions.append(button("edit", () => openEditor(record.id)), button("remove", () => removeProject(record.id)));
      if (record.sync_state === "conflict") actions.prepend(button("resolve", () => resolve(record.id), "records-primary"));
      item.append(copy, actions); list.append(item);
    });
  }
  async function synchronize() {
    if (!library) return;
    if (!root.navigator.onLine) { feedback("offline"); return; }
    if (syncPromise) return syncPromise;
    const current = library, epoch = generation;
    syncing = true;
    syncPromise = (async () => {
      try {
        await refresh();
        await current.sync();
        if (epoch !== generation || current !== library) return;
        await refresh();
        const pending = await current.pendingCount();
        const drafts = current.editorDraftCount ? await current.editorDraftCount() : 0;
        if (epoch !== generation) return;
        if (records.some((record) => record.sync_state === "conflict")) feedback("conflict", "error");
        else feedback(pending ? "unavailable" : drafts ? "draftState" : "cloudSaved", pending ? "error" : "info");
      } catch (error) {
        if (epoch === generation) reportError(error);
      } finally {
        if (epoch === generation) { syncing = false; syncPromise = null; await refresh(); }
      }
    })();
    return syncPromise;
  }
  function requestSync() { if (library && root.navigator.onLine) Promise.resolve(synchronize()).catch(reportError); }
  function currentDraft() {
    return { title: $("records-edit-title").value.trim(), notes: $("records-edit-notes").value, status: $("records-edit-status").value };
  }
  function draftValue() {
    if (!editorBase) return null;
    return Object.assign(currentDraft(), { base_version: editorBase.version, base_title: editorBase.title || "", base_notes: editorBase.notes || "", base_status: editorBase.status || "to_research" });
  }
  async function persistEditorDraft() {
    const current = library, base = editorBase, value = draftValue();
    if (!current || !base || !value || !editorDirty || !current.saveEditorDraft) return;
    await current.saveEditorDraft(base.id, value);
  }
  async function mayDiscardEditor() {
    if (!editorDirty) return true;
    const current = library, epoch = generation, base = editorBase;
    const choice = await ask("discardTitle", "discardMessage", [["cancel", "cancel"], ["discard", "discard", true]]);
    if (choice !== "discard" || epoch !== generation || current !== library) return false;
    root.clearTimeout(draftTimer);
    if (base && current.clearEditorDraft) await current.clearEditorDraft(base.id);
    if (epoch !== generation || current !== library) return false;
    editorDirty = false;
    return true;
  }
  async function openEditor(id) {
    if (!await mayDiscardEditor()) return;
    const record = records.find((value) => value.id === id);
    if (!record || !library) return;
    const current = library, epoch = generation;
    // Do not let typing land in the previous record while its replacement loads.
    $("records-editor").hidden = true;
    const savedDraft = current.getEditorDraft ? await current.getEditorDraft(id) : null;
    if (epoch !== generation || current !== library) return;
    editorBase = JSON.parse(JSON.stringify(record)); editorMerge = null; editorDirty = Boolean(savedDraft);
    if (savedDraft) Object.assign(editorBase, { version: savedDraft.base_version, title: savedDraft.base_title, notes: savedDraft.base_notes, status: savedDraft.base_status });
    $("records-edit-id").value = id;
    $("records-edit-title").value = savedDraft ? savedDraft.title : record.title || "";
    $("records-edit-notes").value = savedDraft ? savedDraft.notes : record.notes || "";
    $("records-edit-status").value = savedDraft ? savedDraft.status : STATES.includes(record.status) ? record.status : "to_research";
    $("records-editor").hidden = false;
    openSaved(); $("records-editor-heading").focus();
  }
  async function saveEditor() {
    if (!editorBase || !library || !$("records-edit-form").reportValidity()) return false;
    const current = library, epoch = generation, originalBase = editorBase;
    root.clearTimeout(draftTimer);
    await persistEditorDraft();
    if (epoch !== generation || current !== library || editorBase !== originalBase) return false;
    const draft = currentDraft();
    const latest = (await current.list()).find((record) => record.id === editorBase.id);
    if (epoch !== generation || current !== library || editorBase !== originalBase) return false;
    if (!latest) { feedback("conflict", "error"); return false; }
    if (latest.version !== editorBase.version && (latest.notes !== editorBase.notes || latest.status !== editorBase.status || latest.title !== editorBase.title) && !editorMerge) {
      const choice = await ask("conflictTitle", "conflictMessage", [["cancel", "cancel"], ["remote", "keepRemote"], ["local", "keepLocal"], ["merge", "merge"]], [["localVersion", draft.notes], ["remoteVersion", latest.notes || t("deletedVersion")]]);
      if (epoch !== generation || current !== library) return false;
      if (choice === "remote") { if (current.clearEditorDraft) await current.clearEditorDraft(latest.id); editorDirty = false; await openEditor(latest.id); return false; }
      if (choice === "merge") { editorBase = JSON.parse(JSON.stringify(latest)); editorMerge = true; editorDirty = true; return false; }
      if (choice !== "local") return false;
    }
    if (latest.sync_state === "conflict") await current.resolveConflict(latest.id, "merge", draft);
    else await current.updateRecord(latest.id, draft);
    if (current.clearEditorDraft) await current.clearEditorDraft(latest.id);
    if (epoch !== generation || current !== library) return false;
    editorDirty = false; editorMerge = null;
    await refresh();
    const saved = records.find((record) => record.id === latest.id);
    if (saved) editorBase = JSON.parse(JSON.stringify(saved));
    toast("notesSaved"); requestSync(); return true;
  }
  async function saveProject(project, restore = false) {
    if (!library) {
      if (!root.navigator.onLine) { openSaved(); feedback("firstOnline", "error"); return; }
      ownWrite(root.sessionStorage, intentKey, JSON.stringify({ project, returnPath: root.location.pathname + root.location.search + root.location.hash }));
      openSaved(); await signIn(); return;
    }
    const canonical = core().normalizeUrl(project.url);
    const existing = records.find((record) => record.canonical_url === canonical && !record.deleted_at);
    if (existing && !restore) { await openEditor(existing.id); return; }
    const current = library, epoch = generation;
    try {
      await current.saveProject(project, { restore });
      if (epoch !== generation || current !== library) return;
      await refresh(); toast("localSaved"); requestSync();
    } catch (error) {
      if (epoch !== generation) return;
      if (error && error.code === "restore_required") {
        const choice = await ask("restoreTitle", "restoreMessage", [["cancel", "cancel"], ["restore", "restore"]]);
        if (epoch !== generation || current !== library) return;
        if (choice === "restore") await saveProject(project, true);
      } else throw error;
    }
  }
  async function removeProject(id) {
    if (!library) return;
    const current = library, epoch = generation;
    if (await ask("removeTitle", "removeMessage", [["cancel", "cancel"], ["remove", "remove", true]]) !== "remove") return;
    if (epoch !== generation || current !== library) return;
    await current.removeRecord(id);
    if (current.clearEditorDraft) await current.clearEditorDraft(id);
    if (epoch !== generation || current !== library) return;
    if (editorBase && editorBase.id === id) { editorBase = null; editorDirty = false; $("records-editor").hidden = true; }
    await refresh(); toast("removed"); requestSync();
  }
  async function resolve(id) {
    const record = records.find((value) => value.id === id);
    if (!record || !record.conflict || !library) return;
    const current = library, epoch = generation;
    const remote = record.conflict.remote;
    const local = record.conflict.local || record;
    const choice = await ask("conflictTitle", "conflictMessage", [["cancel", "cancel"], ["remote", "keepRemote"], ["local", "keepLocal"], ["merge", "merge"]], [["localVersion", local.notes || ""], ["remoteVersion", !remote || remote.deleted_at ? t("deletedVersion") : remote.notes || ""]]);
    if (epoch !== generation || current !== library) return;
    if (choice === "cancel") return;
    if (choice === "merge") { await openEditor(id); editorMerge = true; editorDirty = true; return; }
    try { await current.resolveConflict(id, choice); }
    catch (error) {
      if (error && error.code === "restore_required") {
        const confirm = await ask("restoreTitle", "restoreMessage", [["cancel", "cancel"], ["restore", "restore"]]);
        if (epoch !== generation || current !== library) return;
        if (confirm === "restore") await current.saveProject(local, { restore: true });
      } else throw error;
    }
    await refresh(); requestSync();
  }
  function openSaved() {
    if (root.location.hash !== "#saved") root.location.hash = "saved";
    showView();
  }
  function showView() {
    const opened = root.location.hash === "#saved";
    const wasOpen = !view.hidden;
    if (opened && view.hidden) {
      readingScroll = root.scrollY;
      returnHash = previousHash;
      lastFocus = document.activeElement;
    }
    const briefing = $("briefing-view");
    if (briefing) briefing.hidden = opened;
    view.hidden = !opened;
    if (opened && !wasOpen) { $("records-heading").focus({ preventScroll: true }); root.scrollTo(0, 0); requestSync(); }
    else if (!opened && wasOpen) root.scrollTo(0, readingScroll);
    const entry = $("saved-open");
    if (entry) entry.setAttribute("aria-current", opened ? "page" : "false");
  }
  async function backToBriefing(event) {
    event.preventDefault();
    if (!await mayDiscardEditor()) return;
    editorDirty = false;
    root.history.replaceState(null, "", root.location.pathname + root.location.search + returnHash);
    previousHash = returnHash;
    view.hidden = true;
    if ($("briefing-view")) $("briefing-view").hidden = false;
    root.scrollTo(0, readingScroll);
    if (lastFocus && lastFocus.isConnected) lastFocus.focus({ preventScroll: true });
    const entry = $("saved-open"); if (entry) entry.removeAttribute("aria-current");
  }
  async function signIn() {
    if (!client || !config || !config.enabled) return;
    if (!root.navigator.onLine) { feedback("firstOnline", "error"); return; }
    if (!ownRead(root.sessionStorage, intentKey)) ownWrite(root.sessionStorage, intentKey, JSON.stringify({ returnPath: root.location.pathname + root.location.search + (root.location.hash === "#saved" ? "" : root.location.hash) }));
    sessionBlocked = false;
    $("records-login").disabled = true;
    try {
      const result = await client.auth.signInWithOAuth({ provider: "github", options: { redirectTo: config.redirectUrl } });
      if (result.error) throw new Error("sign-in");
    } catch (_) { feedback("loginFailed", "error"); $("records-login").disabled = false; }
  }
  async function restoreIntent() {
    const value = ownRead(root.sessionStorage, intentKey);
    if (!value || !library) return;
    ownRemove(root.sessionStorage, intentKey);
    try {
      const intent = JSON.parse(value);
      const returnPath = safeReturnPath(intent.returnPath, config.redirectUrl);
      if (intent.project) await saveProject(core().validateProject(intent.project));
      if (returnPath && returnPath !== root.location.pathname + root.location.search + root.location.hash) root.location.replace(returnPath);
    } catch (_) { feedback("invalidRecord", "error"); }
  }
  function download(text, name, type) {
    const objectUrl = root.URL.createObjectURL(new Blob([text], { type }));
    const link = node("a"); link.href = objectUrl; link.download = name;
    document.body.append(link); link.click(); link.remove();
    root.setTimeout(() => root.URL.revokeObjectURL(objectUrl), 1000);
  }
  async function backupWithDraft() {
    const current = library, epoch = generation;
    await persistEditorDraft();
    if (epoch !== generation || current !== library) throw Object.assign(new Error("session"), { code: "session_required" });
    const backup = await current.exportBackup();
    if (epoch !== generation || current !== library) throw Object.assign(new Error("session"), { code: "session_required" });
    if (editorDirty && editorBase && Array.isArray(backup.records)) {
      const draft = currentDraft();
      const matching = backup.records.find((record) => record.url && core().normalizeUrl(record.url) === editorBase.canonical_url);
      if (matching) Object.assign(matching, draft, {title: draft.title || matching.title});
    }
    core().validateBackup(backup);
    return backup;
  }
  async function exportRecords(format) {
    if (!library) return;
    const current = library, epoch = generation;
    const backup = await backupWithDraft();
    if (epoch !== generation || current !== library) return;
    const date = new Date().toISOString().slice(0, 10);
    if (format === "json") download(JSON.stringify(backup, null, 2) + "\n", "xait-projects-" + date + ".json", "application/json");
    else download(core().toMarkdown(backup), "xait-projects-" + date + ".md", "text/markdown;charset=utf-8");
    toast("exported");
  }
  async function importRecords(file) {
    if (!library || !file) return;
    const current = library, epoch = generation, targetLabel = userLabel;
    if (file.size > 5 * 1024 * 1024) { feedback("badBackup", "error"); return; }
    let parsed;
    try { parsed = JSON.parse(await file.text()); core().validateBackup(parsed); }
    catch (_) { feedback("badBackup", "error"); return; }
    if (epoch !== generation || current !== library) return;
    if (await ask("importTitle", "importMessage", [["cancel", "cancel"], ["import", "importJson"]], [["account", targetLabel]]) !== "import") return;
    if (epoch !== generation || current !== library) return;
    await current.importBackup(parsed);
    if (epoch !== generation) return;
    await refresh(); feedback("imported"); requestSync();
  }
  async function signOut() {
    if (!library || !client) return;
    const current = library, epoch = generation, activeClient = client;
    await persistEditorDraft();
    const pending = await current.pendingCount();
    const drafts = current.editorDraftCount ? await current.editorDraftCount() : 0;
    if (epoch !== generation || current !== library || client !== activeClient) return;
    if (editorDirty || pending || drafts || records.some((record) => record.sync_state === "conflict")) {
      const choice = await ask("signoutTitle", "signoutMessage", [["cancel", "cancel"], ["sync", "sync"], ["export", "exportFirst"], ["discard", "discardAndOut", true]]);
      if (epoch !== generation || current !== library || choice === "cancel") return;
      if (choice === "export") { await exportRecords("json"); return; }
      if (choice === "sync") {
        if (editorDirty && !await saveEditor()) return;
        await synchronize();
        if (epoch !== generation || current !== library || await current.pendingCount() || current.editorDraftCount && await current.editorDraftCount() || records.some((record) => record.sync_state === "conflict")) return;
      }
      if (!["discard", "sync"].includes(choice)) return;
    }
    sessionBlocked = true;
    lock();
    activeClient.auth.stopAutoRefresh();
    if (subscription) subscription.unsubscribe();
    subscription = null;
    let cacheCleared = true;
    try { await current.clearLocal(); } catch (_) { cacheCleared = false; }
    try { await activeClient.auth.signOut({ scope: "local" }); } catch (_) { /* Local session cleanup below also runs offline. */ }
    for (const suffix of ["", "-code-verifier", "-user"]) ownRemove(root.localStorage, storageKey + suffix);
    ownRemove(root.localStorage, lastIdentityKey); ownRemove(root.sessionStorage, intentKey);
    client = null; syncPromise = null; syncing = false;
    setupClient(); renderGate(null); feedback(cacheCleared ? "signoutDone" : "signoutPartial", cacheCleared ? "info" : "error");
  }
  function setupClient() {
    if (!root.supabase || !core()) return;
    client = root.supabase.createClient(config.supabaseUrl, config.publishableKey, { auth: { flowType: "pkce", detectSessionInUrl: false, persistSession: true, autoRefreshToken: true, storageKey } });
    const listener = client.auth.onAuthStateChange((_event, session) => {
      if (sessionBlocked) return;
      if (!session || userId && session.user && userId !== session.user.id) lock();
      root.setTimeout(() => { Promise.resolve(onSession(session)).catch(reportError); }, 0);
    });
    subscription = listener.data && listener.data.subscription;
  }
  async function start() {
    const callback = cleanAuthLocation(root.location.href);
    if (callback.changed) root.history.replaceState(null, "", callback.clean);
    localize(); showView();
    try {
      const configNode = $("xait-records-config");
      config = readConfig(configNode ? configNode.content ? configNode.content.textContent : configNode.textContent : "{}");
      if (!config.enabled) { renderGate(); updateButtons(); return; }
      const home = document.querySelector(".sidebar-brand");
      if (!home || !isAllowedRuntime(config, home.href, root.location.href, root.isSecureContext)) { renderGate("foreign"); return; }
      namespace = new URL(config.supabaseUrl).hostname + new URL(config.redirectUrl).pathname;
      storageKey = "xait-records-auth-" + encodeURIComponent(namespace);
      lastIdentityKey = storageKey + "-identity"; intentKey = storageKey + "-intent";
      if (!root.supabase || !core()) { renderGate("sdkMissing"); return; }
      setupClient();
      if (callback.code) {
        const exchanged = await client.auth.exchangeCodeForSession(callback.code);
        if (exchanged.error) { renderGate(); feedback("loginFailed", "error"); openSaved(); return; }
        await onSession(exchanged.data.session);
      } else {
        const current = await client.auth.getSession();
        await onSession(current.data && current.data.session);
        if (callback.hasError) { openSaved(); feedback("loginFailed", "error"); }
      }
      renderGateIfNeeded();
      pollTimer = root.setInterval(() => { if (!document.hidden && root.location.hash === "#saved") requestSync(); }, 30000);
    } catch (_) { renderGate("sdkMissing"); }
  }
  function renderGateIfNeeded() { if (!library) renderGate(); }
  $("records-back").addEventListener("click", (event) => { backToBriefing(event).catch(reportError); });
  $("records-login").addEventListener("click", () => { signIn().catch(reportError); });
  $("records-search").addEventListener("input", renderList);
  $("records-filter").addEventListener("change", renderList);
  $("records-sync").addEventListener("click", () => { synchronize().catch(reportError); });
  $("records-signout").addEventListener("click", () => { signOut().catch(reportError); });
  $("records-manual-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const title = $("records-manual-title").value.trim(), url = $("records-manual-url").value.trim();
    const current = library, epoch = generation;
    saveProject({ title, url, source_id: "manual", source_issue_date: null }).then(() => { if (library && current === library && epoch === generation) { $("records-manual-form").reset(); $("records-add").open = false; } }).catch(reportError);
  });
  $("records-edit-form").addEventListener("input", () => {
    editorDirty = true;
    root.clearTimeout(draftTimer);
    draftTimer = root.setTimeout(() => { persistEditorDraft().catch(reportError); }, 300);
  });
  $("records-edit-form").addEventListener("submit", (event) => { event.preventDefault(); saveEditor().catch(reportError); });
  $("records-editor-close").addEventListener("click", () => { mayDiscardEditor().then((allowed) => { if (allowed) { editorDirty = false; $("records-editor").hidden = true; } }).catch(reportError); });
  $("records-export-json").addEventListener("click", () => { exportRecords("json").catch(reportError); });
  $("records-export-markdown").addEventListener("click", () => { exportRecords("markdown").catch(reportError); });
  $("records-import").addEventListener("click", () => { $("records-import-file").click(); });
  $("records-import-file").addEventListener("change", (event) => { const file = event.target.files[0]; event.target.value = ""; importRecords(file).catch(reportError); });
  document.addEventListener("click", (event) => {
    const action = event.target.closest("[data-save-project]");
    if (!action || action.disabled) return;
    event.preventDefault();
    const project = { title: action.dataset.projectTitle, url: action.dataset.projectUrl, source_id: action.dataset.projectSource || null, source_issue_date: action.dataset.projectIssue || null };
    saveProject(project).catch(reportError);
  });
  root.addEventListener("hashchange", () => {
    if (root.location.hash !== "#saved") previousHash = root.location.hash;
    showView();
  });
  document.addEventListener("xait:languagechange", localize);
  new MutationObserver(localize).observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });
  root.addEventListener("online", requestSync);
  root.addEventListener("offline", () => { if (library) feedback("offline"); });
  root.addEventListener("focus", requestSync);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) requestSync(); });
  root.addEventListener("beforeunload", (event) => { if (editorDirty) { event.preventDefault(); event.returnValue = ""; } });
  root.addEventListener("pagehide", () => { if (pollTimer) root.clearInterval(pollTimer); });
  start().catch(() => { renderGate("sdkMissing"); });
})(typeof window !== "undefined" ? window : globalThis);
