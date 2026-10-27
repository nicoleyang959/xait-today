/* Private project records: storage and synchronization, with no account discovery. */
(function (root, factory) {
  "use strict";
  const api = factory(root);
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.XaitRecordsCore = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function (root) {
  "use strict";

  const STATUSES = Object.freeze(["to_research", "tried", "watching"]);
  const TRACKING = new Set(["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id", "utm_source_platform", "utm_creative_format", "utm_marketing_tactic", "fbclid", "gclid", "dclid", "msclkid", "mc_cid", "mc_eid"]);
  const SENSITIVE = new Set(["access_token", "api_key", "apikey", "auth", "authorization", "cookie", "key", "code", "sig", "password", "secret", "session", "sessionid", "token", "refresh_token", "signature", "credential", "private_key"]);
  const PROJECT_FIELDS = Object.freeze(["url", "title", "source_id", "source_issue_date", "notes", "status"]);
  const SOURCES = new Set(["manual", "github-trending", "weekly-high-stars", "product-hunt", "product-hunt-ranking"]);
  const BACKUP_FIELDS = new Set(PROJECT_FIELDS);
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  const CONTROL = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/;
  const MAX_RECORDS = 1000;
  const clone = (value) => value === undefined ? undefined : JSON.parse(JSON.stringify(value));
  const own = (object, key) => Object.prototype.hasOwnProperty.call(object, key);

  class RecordsError extends Error {
    constructor(code, message) {
      super(message || code);
      this.name = "RecordsError";
      this.code = code;
    }
  }
  const fail = (code) => { throw new RecordsError(code); };
  const now = () => new Date().toISOString();
  function newId() {
    if (root.crypto && typeof root.crypto.randomUUID === "function") return root.crypto.randomUUID();
    if (!root.crypto || !root.crypto.getRandomValues) return fail("secure_random_unavailable");
    const bytes = root.crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 15) | 64;
    bytes[8] = (bytes[8] & 63) | 128;
    const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
    return [hex.slice(0, 8), hex.slice(8, 12), hex.slice(12, 16), hex.slice(16, 20), hex.slice(20)].join("-");
  }
  async function urlKey(canonical) {
    if (!root.crypto || !root.crypto.subtle) fail("secure_random_unavailable");
    const digest = await root.crypto.subtle.digest("SHA-256", new TextEncoder().encode(canonical));
    return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
  }
  function plain(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value) && (Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null);
  }
  function text(value, maximum, empty) {
    if (typeof value !== "string" || (!empty && !value.trim()) || Array.from(value).length > maximum || CONTROL.test(value)) fail("invalid_text");
    try { encodeURIComponent(value); } catch (_) { fail("invalid_text"); }
    return value;
  }
  function ipv4Public(host) {
    const parts = host.split(".");
    if (parts.length !== 4 || parts.some((part) => !/^\d{1,3}$/.test(part) || String(Number(part)) !== part || Number(part) > 255)) return false;
    const [a, b, c] = parts.map(Number);
    if (a === 0 || a === 10 || a === 127 || a >= 224) return false;
    if ((a === 100 && b >= 64 && b <= 127) || (a === 169 && b === 254) || (a === 172 && b >= 16 && b <= 31)) return false;
    if (a === 192 && ((b === 168) || (b === 0 && (c === 0 || c === 2)))) return false;
    if (a === 198 && ((b === 18 || b === 19) || (b === 51 && c === 100))) return false;
    if (a === 203 && b === 0 && c === 113) return false;
    return true;
  }
  function ipv6Public(host) {
    const parts = host.replace(/^\[|\]$/g, "").split(":");
    const first = parseInt(parts[0] || "0", 16);
    if (!(first >= 0x2000 && first <= 0x3fff)) return false;
    const second = parseInt(parts[1] || "0", 16);
    if (first === 0x2001 && (second === 0x0db8 || second < 0x200)) return false;
    if (first === 0x2002 || (first === 0x3fff && second < 0x1000)) return false;
    return true;
  }
  function queryKey(piece) {
    try { return decodeURIComponent(piece.split("=", 1)[0].replace(/\+/g, " ")).toLowerCase(); }
    catch (_) { return fail("invalid_url"); }
  }
  function rejectCredentialMarkers(component) {
    let decoded = component;
    for (let pass = 0; pass < 3; pass += 1) {
      let next;
      try { next = decodeURIComponent(decoded.replace(/\+/g, " ")); }
      catch (_) { fail("invalid_url"); }
      decoded = next;
      if (/(?:^|[?&#/;])[^?&#/;:=]*(?:auth|credential|token|secret|password|cookie|session|signature|private[_-]?key|api[_-]?key)[^?&#/;:=]*\s*[:=]/i.test(decoded)) fail("unsafe_url");
      for (const piece of decoded.replace(/[?/;]/g, "&").split("&")) {
        if (SENSITIVE.has(piece.split(/[=:]/, 1)[0].trim().toLowerCase())) fail("unsafe_url");
      }
      if (!/%[0-9a-f]{2}/i.test(decoded)) break;
    }
  }
  function normalizeUrl(value) {
    text(value, 2048, false);
    if (/[\s<>"`{}\\]/.test(value) || /%(?:00|0a|0d)/i.test(value)) fail("invalid_url");
    const match = /^(https?):\/\/([^/?#]+)([^?#]*)(?:\?([^#]*))?(?:#(.*))?$/i.exec(value);
    if (!match || match[2].includes("@")) fail("invalid_url");
    let parsed;
    try { parsed = new URL(value); } catch (_) { return fail("invalid_url"); }
    if (parsed.username || parsed.password || !parsed.hostname) fail("invalid_url");
    const authority = match[2];
    const ipv6 = authority.startsWith("[");
    const authorityMatch = ipv6 ? /^(\[[0-9a-f:]+\])(?::([0-9]+))?$/i.exec(authority) : /^([^:]+)(?::([0-9]+))?$/.exec(authority);
    if (!authorityMatch) fail("invalid_url");
    const scheme = match[1].toLowerCase();
    let host = authorityMatch[1].toLowerCase().replace(/\.+$/, "");
    const unbracketed = host.replace(/^\[|\]$/g, "");
    if (/%/.test(host) || /^0x/i.test(host) || /^\d+$/.test(host)) fail("unsafe_url");
    if (["localtest.me", "lvh.me", "nip.io", "sslip.io", "xip.io"].some((domain) => host === domain || host.endsWith("." + domain))) fail("unsafe_url");
    if (ipv6) {
      if (!ipv6Public(parsed.hostname)) fail("unsafe_url");
    } else if (/^[\d.]+$/.test(host)) {
      if (!ipv4Public(host)) fail("unsafe_url");
    } else {
      if (!host.includes(".") || host === "localhost" || /\.(localhost|local|internal|lan|home)$/.test(host)) fail("unsafe_url");
      if (parsed.hostname !== host && /^[\d.]+$/.test(parsed.hostname)) fail("unsafe_url");
      // Keep the accepted host spelling identical to the SQL normalizer. Raw
      // Unicode is not implicitly converted to a different queued identity.
      if (unbracketed.length > 253 || !/^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$/.test(host) || host.includes("..")) fail("unsafe_url");
    }
    if (authorityMatch[2] && authorityMatch[2].length > 5) fail("invalid_url");
    const port = authorityMatch[2] ? Number(authorityMatch[2]) : null;
    if (port !== null && (port < 1 || port > 65535)) fail("unsafe_url");
    if (port !== null && !((scheme === "http" && port === 80) || (scheme === "https" && port === 443))) host += ":" + String(port);
    rejectCredentialMarkers(match[4] || "");
    rejectCredentialMarkers(match[5] || "");
    const query = (match[4] || "").split("&").filter((piece) => {
      const key = queryKey(piece);
      if (SENSITIVE.has(key) || key.startsWith("x_amz_")) fail("unsafe_url");
      return !TRACKING.has(key);
    }).join("&");
    return scheme + "://" + host + match[3] + (query ? "?" + query : "") + (match[5] !== undefined && match[5] !== "" ? "#" + match[5] : "");
  }
  function validDate(value) {
    if (value === null || value === undefined || value === "") return null;
    if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value) || Number.isNaN(Date.parse(value + "T00:00:00Z")) || new Date(value + "T00:00:00Z").toISOString().slice(0, 10) !== value) fail("invalid_date");
    return value;
  }
  function validateProject(value, strict) {
    if (!plain(value)) fail("invalid_record");
    if (strict && Object.keys(value).some((key) => !BACKUP_FIELDS.has(key))) fail("unknown_field");
    const url = text(value.url, 2048, false);
    const canonical = normalizeUrl(url);
    const source = value.source_id == null || value.source_id === "" ? "manual" : text(value.source_id, 80, false);
    if (!SOURCES.has(source)) fail("invalid_source");
    const status = value.status === undefined ? "to_research" : value.status;
    if (!STATUSES.includes(status)) fail("invalid_status");
    return {
      url, canonical_url: canonical, title: text(value.title, 200, false), source_id: source,
      source_issue_date: validDate(value.source_issue_date), notes: text(value.notes === undefined ? "" : value.notes, 5000, true), status
    };
  }
  function projectPayload(value) {
    return Object.fromEntries(PROJECT_FIELDS.map((field) => [field, value[field] == null ? null : value[field]]));
  }
  function validateRemote(value) {
    if (!plain(value) || !UUID.test(value.id || "") || !Number.isSafeInteger(value.version) || value.version < 1 || typeof value.created_at !== "string" || typeof value.updated_at !== "string") fail("invalid_remote");
    if (Number.isNaN(Date.parse(value.created_at)) || Number.isNaN(Date.parse(value.updated_at)) || typeof value.url_key !== "string" || !/^[0-9a-f]{64}$/.test(value.url_key)) fail("invalid_remote");
    if (value.deleted_at) {
      if (typeof value.deleted_at !== "string" || Number.isNaN(Date.parse(value.deleted_at))) fail("invalid_remote");
      return { id: value.id, url_key:value.url_key, version: value.version, created_at: value.created_at, updated_at: value.updated_at,
        deleted_at: value.deleted_at, canonical_url: null, url: null, title: null, source_id: null, source_issue_date: null, notes: null, status: null };
    }
    const project = validateProject(value, false);
    if (value.canonical_url !== project.canonical_url) fail("invalid_remote");
    return Object.assign(project, {id:value.id, url_key:value.url_key, version:value.version, created_at:value.created_at, updated_at:value.updated_at, deleted_at:null});
  }
  function initialState() { return {schemaVersion:1, records:{}, outbox:[], editor_drafts:{}, next_order:1}; }
  function validateState(state) {
    if (!plain(state) || state.schemaVersion !== 1 || !plain(state.records) || !Array.isArray(state.outbox) || !Number.isSafeInteger(state.next_order)) fail("storage_corrupt");
    if (state.editor_drafts === undefined) state.editor_drafts = {};
    if (!plain(state.editor_drafts)) fail("storage_corrupt");
    return state;
  }

  class MemoryStore {
    constructor() { this.state = initialState(); this.tail = Promise.resolve(); this.failNext = false; }
    async read() { await this.tail; return clone(this.state); }
    transact(callback) {
      const operation = this.tail.then(() => {
        const draft = clone(this.state);
        const result = callback(draft);
        if (result && typeof result.then === "function") fail("async_transaction");
        if (this.failNext) { this.failNext = false; fail("storage_unavailable"); }
        this.state = draft;
        return clone(result);
      });
      this.tail = operation.catch(() => {});
      return operation;
    }
    clear() { return this.transact((state) => { Object.assign(state, initialState()); }); }
  }
  class IndexedStore {
    constructor(db, key) { this.db = db; this.key = key; this.closed = false; }
    close() { if (!this.closed) { this.closed = true; this.db.close(); } }
    read() {
      return new Promise((resolve, reject) => {
        const transaction = this.db.transaction("accounts", "readonly");
        const request = transaction.objectStore("accounts").get(this.key);
        let value;
        request.onsuccess = () => { value = request.result || initialState(); };
        transaction.oncomplete = () => { try { resolve(clone(validateState(value))); } catch (error) { reject(error); } };
        transaction.onerror = transaction.onabort = () => reject(new RecordsError("storage_unavailable"));
      });
    }
    transact(callback) {
      return new Promise((resolve, reject) => {
        let result, failure;
        let transaction;
        try { transaction = this.db.transaction("accounts", "readwrite"); } catch (_) { reject(new RecordsError("storage_unavailable")); return; }
        const table = transaction.objectStore("accounts");
        const request = table.get(this.key);
        request.onsuccess = () => {
          try {
            const state = clone(validateState(request.result || initialState()));
            result = callback(state);
            if (result && typeof result.then === "function") fail("async_transaction");
            table.put(state, this.key);
          } catch (error) { failure = error; transaction.abort(); }
        };
        transaction.oncomplete = () => resolve(clone(result));
        transaction.onerror = transaction.onabort = () => reject(failure || new RecordsError("storage_unavailable"));
      });
    }
    clear() {
      return new Promise((resolve, reject) => {
        const remove = (db, reopened) => {
          let transaction;
          try { transaction = db.transaction("accounts", "readwrite"); }
          catch (_) { if (reopened) db.close(); reject(new RecordsError("storage_unavailable")); return; }
          transaction.objectStore("accounts").delete(this.key);
          transaction.oncomplete = () => { if (reopened) db.close(); resolve(); };
          transaction.onerror = transaction.onabort = () => { if (reopened) db.close(); reject(new RecordsError("storage_unavailable")); };
        };
        if (!this.closed) { remove(this.db, false); return; }
        // Auth locking closes old connections. Clearing that account later is
        // still possible, through a short-lived connection to the same store.
        let request;
        try { request = root.indexedDB.open("xait-project-records-v1", 1); }
        catch (_) { reject(new RecordsError("storage_unavailable")); return; }
        request.onerror = request.onblocked = () => reject(new RecordsError("storage_unavailable"));
        request.onsuccess = () => remove(request.result, true);
      });
    }
  }
  function openStore(namespace, userId) {
    if (typeof namespace !== "string" || !namespace || typeof userId !== "string" || !UUID.test(userId)) return Promise.reject(new RecordsError("invalid_account"));
    if (!root.indexedDB) return Promise.reject(new RecordsError("storage_unavailable"));
    return new Promise((resolve, reject) => {
      let request;
      try { request = root.indexedDB.open("xait-project-records-v1", 1); } catch (_) { reject(new RecordsError("storage_unavailable")); return; }
      request.onupgradeneeded = () => { if (!request.result.objectStoreNames.contains("accounts")) request.result.createObjectStore("accounts"); };
      request.onerror = request.onblocked = () => reject(new RecordsError("storage_unavailable"));
      request.onsuccess = () => resolve(new IndexedStore(request.result, JSON.stringify([namespace, userId])));
    });
  }
  function createSupabaseTransport(client, accountId) {
    if (!client || typeof client.rpc !== "function") fail("invalid_transport");
    if (typeof accountId !== "string" || !UUID.test(accountId)) fail("invalid_account");
    const expectedAccount = accountId;
    const invoke = async (name, args) => {
      let result;
      try { result = await client.rpc(name, args); }
      catch (_) { throw new RecordsError("sync_failed"); }
      if (!result || result.error) {
        const error = result && result.error;
        const categories = {
          "P0001:record_limit_reached":"record_limit",
          "P0001:storage_limit_reached":"storage_limit",
          "28000:account_changed":"session_required",
          "28000:authentication_required":"session_required",
          "22023:notes_too_long":"invalid_record"
        };
        // Only exact server-owned error identifiers cross this boundary. Raw
        // messages, diagnostic detail and provider payloads stay discarded.
        const key = error && typeof error.code === "string" && typeof error.message === "string" ? error.code + ":" + error.message : "";
        throw new RecordsError(own(categories, key) ? categories[key] : "sync_failed");
      }
      return result.data;
    };
    return {
      list: (after) => invoke("list_my_records", {p_account_id:expectedAccount, p_after_id:after || null, p_limit:100}),
      mutate: (operation) => invoke("apply_record_mutation", {
        p_account_id:expectedAccount,
        p_mutation_id:operation.mutation_id, p_record_id:operation.record_id,
        p_operation:operation.operation, p_expected_version:operation.expected_version,
        p_payload:clone(operation.payload)
      })
    };
  }
  function validateBackup(value) {
    if (!plain(value) || value.schemaVersion !== 1 || Object.keys(value).some((key) => !["schemaVersion", "exportedAt", "records"].includes(key)) || !Array.isArray(value.records) || value.records.length > MAX_RECORDS) fail("invalid_backup");
    if (typeof value.exportedAt !== "string" || Number.isNaN(Date.parse(value.exportedAt))) fail("invalid_backup");
    const projects = value.records.map((record) => validateProject(record, true));
    if (new Set(projects.map((record) => record.canonical_url)).size !== projects.length) fail("duplicate_backup_url");
    return projects;
  }

  class Library {
    constructor(options) {
      if (!options || !options.store || typeof options.store.transact !== "function") fail("invalid_store");
      this.store = options.store;
      this.transport = options.transport || null;
      this.onChange = typeof options.onChange === "function" ? options.onChange : () => {};
      this.stopped = false;
      this.generation = 0;
      this.syncing = null;
    }
    _guard(epoch) { if (this.stopped || (epoch !== undefined && epoch !== this.generation)) fail("stopped"); }
    _notify() { if (!this.stopped) { try { this.onChange(); } catch (_) { /* A UI failure cannot undo a committed transaction. */ } } }
    async _change(callback, epoch) {
      this._guard(epoch);
      const result = await this.store.transact((state) => { this._guard(epoch); return callback(validateState(state)); });
      this._guard(epoch);
      this._notify();
      return result;
    }
    async init() {
      this._guard();
      await this._change((state) => { state.outbox.forEach((op) => { op.in_flight = false; }); });
      return this;
    }
    async list() {
      this._guard();
      const state = validateState(await this.store.read());
      this._guard();
      return Object.values(state.records).filter((record) => !record.deleted_at || record.sync_state === "conflict").sort((a, b) => (b.updated_at || "").localeCompare(a.updated_at || "") || a.id.localeCompare(b.id)).map((record) => Object.assign(clone(record), {has_editor_draft:own(state.editor_drafts, record.id)}));
    }
    async pendingCount() { this._guard(); const state = await this.store.read(); this._guard(); return state.outbox.length; }
    async saveEditorDraft(id, payload) {
      this._guard();
      if (!UUID.test(id) || !plain(payload) || Object.keys(payload).some((key) => !["title", "notes", "status", "base_version", "base_title", "base_notes", "base_status"].includes(key))) fail("invalid_draft");
      // This local-only transaction belongs to the captured account store. Once
      // issued it may finish during an auth lock, but it never enqueues or sends
      // a cloud write and cannot notify the new account's view.
      const result = await this.store.transact((state) => {
        validateState(state);
        const record = state.records[id];
        if (!record) fail("not_found");
        const previous = state.editor_drafts[id];
        const draft = {
          title:text(payload.title === undefined ? record.title || "" : payload.title, 200, true),
          notes:text(payload.notes === undefined ? record.notes || "" : payload.notes, 5000, true),
          status:payload.status === undefined ? record.status || "to_research" : payload.status,
          base_version:payload.base_version === undefined ? (previous ? previous.base_version : record.version) : payload.base_version,
          base_title:text(payload.base_title === undefined ? (previous ? previous.base_title : record.title || "") : payload.base_title, 200, true),
          base_notes:text(payload.base_notes === undefined ? (previous ? previous.base_notes : record.notes || "") : payload.base_notes, 5000, true),
          base_status:payload.base_status === undefined ? (previous ? previous.base_status : record.status || "to_research") : payload.base_status
        };
        if (!STATUSES.includes(draft.status) || !STATUSES.includes(draft.base_status) || !Number.isSafeInteger(draft.base_version) || draft.base_version < 0) fail("invalid_draft");
        state.editor_drafts[id] = draft;
        return draft;
      });
      this._notify();
      return result;
    }
    async getEditorDraft(id) { this._guard(); const state=validateState(await this.store.read()); this._guard(); return clone(state.editor_drafts[id] || null); }
    async clearEditorDraft(id) { return this._change((state) => { delete state.editor_drafts[id]; }); }
    async editorDraftCount() { this._guard(); const state=validateState(await this.store.read()); this._guard(); return Object.keys(state.editor_drafts).length; }
    _enqueue(state, record, operation, payload, edited) {
      const previous = [...state.outbox].reverse().find((item) => item.record_id === record.id);
      if (previous && !previous.attempted && !previous.in_flight && ["create", "update", "restore"].includes(previous.operation) && operation === "update") {
        previous.payload = Object.assign({}, previous.payload, payload);
        previous.has_edits = true;
      } else {
        state.outbox.push({mutation_id:newId(), record_id:record.id, operation,
          expected_version:record.version || 0, payload:clone(payload), order:state.next_order++, attempted:false, in_flight:false, has_edits:Boolean(edited)});
      }
      record.sync_state = "pending";
      record.last_error = null;
      record.updated_at = now();
    }
    async saveProject(project, options) {
      const value = validateProject(project, false);
      const key = await urlKey(value.canonical_url);
      const restoring = Boolean(options && options.restore);
      return this._change((state) => {
        let record = Object.values(state.records).find((item) => item.canonical_url === value.canonical_url || item.local_canonical_url === value.canonical_url || item.url_key === key);
        if (record) {
          const remote = record.conflict && record.conflict.remote;
          if (record.deleted_at || (remote && remote.deleted_at)) {
            if (!restoring) fail("restore_required");
            const version = remote ? remote.version : record.version;
            const draft = (record.conflict && record.conflict.local) || (record.url && record.title ? projectPayload(record) : null);
            const queued = state.outbox.filter((op) => op.record_id === record.id);
            const attempted = queued.filter((op) => op.attempted).sort((a, b) => a.order - b.order);
            const predecessor = attempted[attempted.length - 1];
            // A failed request may have committed remotely. Its immutable
            // mutation ID must be reconciled before cancelling a local delete
            // or asking to restore; a version-zero restore cannot create a row.
            const nextOperation = predecessor ? (predecessor.operation === "delete" ? "restore" : "update")
              : queued.some((op) => op.operation === "delete") && !remote ? "update" : "restore";
            record = Object.assign({}, value, draft || {}, {id:record.id, url_key:key, version, created_at:record.created_at, updated_at:now(), deleted_at:null});
            delete record.conflict;
            state.records[record.id] = record;
            state.outbox = state.outbox.filter((op) => op.record_id !== record.id || op.attempted);
            this._enqueue(state, record, nextOperation, projectPayload(record), true);
          }
          return record;
        }
        if (Object.values(state.records).filter((item) => !item.deleted_at).length >= MAX_RECORDS) fail("record_limit");
        record = Object.assign({}, value, {id:newId(), url_key:key, version:0, created_at:now(), updated_at:now(), deleted_at:null});
        state.records[record.id] = record;
        this._enqueue(state, record, "create", projectPayload(record), Boolean(record.notes || record.status !== "to_research"));
        return record;
      });
    }
    async updateRecord(id, changes) {
      if (!plain(changes) || Object.keys(changes).some((key) => !["title", "notes", "status"].includes(key))) fail("unknown_field");
      return this._change((state) => {
        const record = state.records[id];
        if (!record || record.deleted_at) fail("not_found");
        const value = validateProject(Object.assign({}, record, changes), false);
        Object.assign(record, value);
        delete state.editor_drafts[id];
        if (record.conflict) { record.conflict.local = projectPayload(record); record.updated_at = now(); }
        else this._enqueue(state, record, "update", {title:record.title, notes:record.notes, status:record.status}, true);
        return record;
      });
    }
    async removeRecord(id) {
      return this._change((state) => {
        const record = state.records[id];
        if (!record) fail("not_found");
        if (record.conflict) fail("conflict_unresolved");
        delete state.editor_drafts[id];
        const operations = state.outbox.filter((op) => op.record_id === id);
        if (record.version === 0 && operations.every((op) => !op.attempted)) {
          delete state.records[id];
          state.outbox = state.outbox.filter((op) => op.record_id !== id);
          return null;
        }
        record.deleted_at = now();
        this._enqueue(state, record, "delete", {}, false);
        return record;
      });
    }
    async resolveConflict(id, choice, mergedPayload) {
      if (!["local", "remote", "merge"].includes(choice)) fail("invalid_choice");
      if (choice === "merge" && (!plain(mergedPayload) || Object.keys(mergedPayload).some((key) => !["title", "notes", "status"].includes(key)))) fail("unknown_field");
      return this._change((state) => {
        const record = state.records[id];
        if (!record || !record.conflict) fail("no_conflict");
        const remote = record.conflict.remote;
        if (!remote) fail("invalid_remote");
        const imported = record.conflict.kind === "import";
        const priorState = imported ? clone(record.conflict.prior_state) : null;
        const priorOutbox = imported ? clone(record.conflict.prior_outbox || []) : [];
        state.outbox = state.outbox.filter((op) => op.record_id !== id);
        delete state.editor_drafts[id];
        if (choice === "remote") {
          if (imported) {
            state.records[id] = priorOutbox.length ? priorState : Object.assign({}, remote, {sync_state:"synced"});
            priorOutbox.forEach((op) => { op.in_flight=false; state.outbox.push(op); });
            return state.records[id];
          }
          state.records[id] = Object.assign({}, remote, {sync_state:"synced"});
          if (remote.version === 0 && !remote.deleted_at) {
            this._enqueue(state, state.records[id], "create", projectPayload(remote), Boolean(remote.notes || remote.status !== "to_research"));
          }
          return state.records[id];
        }
        if (remote.deleted_at) fail("restore_required");
        const payload = choice === "merge" ? Object.assign({}, record.conflict.local, mergedPayload || {}) : record.conflict.local;
        const value = validateProject(Object.assign({}, remote, payload), false);
        const resolved = Object.assign({}, remote, value, {id:remote.id, version:remote.version, deleted_at:null});
        state.records[id] = resolved;
        this._enqueue(state, resolved, remote.version === 0 ? "create" : "update", remote.version === 0 ? projectPayload(resolved) : {title:resolved.title, notes:resolved.notes, status:resolved.status}, true);
        return resolved;
      });
    }
    _conflict(state, id, remote) {
      const record = state.records[id];
      if (!record) return;
      record.conflict = {remote:clone(remote), local:projectPayload(record)};
      record.sync_state = "conflict";
      record.last_error = null;
      state.outbox = state.outbox.filter((op) => op.record_id !== id);
    }
    async _pull(epoch) {
      const remote = [], seen = new Set();
      let after = null;
      while (true) {
        this._guard(epoch);
        const result = await this.transport.list(after);
        this._guard(epoch);
        if (!plain(result) || !Array.isArray(result.records) || result.records.length > 100 || !(result.next_after === null || typeof result.next_after === "string")) fail("invalid_remote");
        let previous = after;
        for (const value of result.records) {
          const record = validateRemote(value);
          const identity = record.id.toLowerCase();
          if (seen.has(identity) || (previous !== null && identity <= previous)) fail("invalid_remote");
          previous = identity;
          seen.add(identity); remote.push(record);
        }
        if (result.next_after === null) break;
        // The service orders by UUID. A nonterminal cursor must identify the
        // final returned row and move strictly forward; this permits any valid
        // history length while rejecting repeated/empty/descending pages.
        if (!UUID.test(result.next_after) || !result.records.length || result.next_after.toLowerCase() !== previous || (after !== null && previous <= after)) fail("invalid_remote");
        after = previous;
      }
      await this._change((state) => {
        for (const record of remote) {
          const local = state.records[record.id];
          if (local && local.sync_state === "conflict") { local.conflict.remote = clone(record); continue; }
          if (local && state.outbox.some((op) => op.record_id === record.id)) continue;
          if (!local || record.version >= local.version) state.records[record.id] = Object.assign({}, record, {sync_state:"synced"});
        }
      }, epoch);
    }
    async _ack(operation, result, epoch) {
      if (!plain(result) || !["applied", "existing", "conflict", "deleted"].includes(result.status)) fail("invalid_remote");
      if (result.status === "deleted" && result.record === null && result.applied_version === null) fail("record_missing");
      const remote = validateRemote(result.record);
      if (!Number.isSafeInteger(result.applied_version) || result.applied_version < 1 || result.applied_version > remote.version) fail("invalid_remote");
      await this._change((state) => {
        const currentOperation = state.outbox.find((op) => op.mutation_id === operation.mutation_id);
        if (!currentOperation) return;
        const oldId = operation.record_id;
        const local = state.records[oldId];
        if (!local) fail("storage_corrupt");
        if (remote.id !== oldId && operation.operation !== "create") fail("invalid_remote");
        state.outbox = state.outbox.filter((op) => op.mutation_id !== operation.mutation_id);
        if (remote.id !== oldId) {
          delete state.records[oldId];
          local.id = remote.id;
          state.records[remote.id] = local;
          state.outbox.forEach((op) => { if (op.record_id === oldId) op.record_id = remote.id; });
        }
        const id = remote.id;
        const successors = state.outbox.filter((op) => op.record_id === id);
        const customExisting = result.status === "existing" && (operation.has_edits || successors.length > 0);
        const appliedVersion = result.applied_version;
        const changedAfterApplication = result.status === "applied" && successors.length > 0 && remote.version > appliedVersion;
        const deletionComplete = operation.operation === "delete" && remote.deleted_at && !successors.length;
        const confirmedRestore = operation.operation === "delete" && result.status === "applied" && remote.deleted_at
          && remote.version === appliedVersion && successors[0]?.operation === "restore";
        if (!deletionComplete && !confirmedRestore && (result.status === "conflict" || result.status === "deleted" || customExisting || changedAfterApplication || (remote.deleted_at && successors.length))) {
          this._conflict(state, id, remote); return;
        }
        if (successors.length) {
          if (successors.some((op) => op.attempted)) fail("storage_corrupt");
          successors.sort((a, b) => a.order - b.order)[0].expected_version = remote.version;
          state.records[id] = Object.assign({}, remote, projectPayload(local), {id, version:remote.version,
            deleted_at:local.deleted_at, updated_at:local.updated_at, sync_state:"pending", last_error:null});
        } else {
          const canonical = local.canonical_url || local.local_canonical_url;
          state.records[id] = Object.assign({}, remote, {sync_state:"synced", last_error:null});
          if (remote.deleted_at) state.records[id].local_canonical_url = canonical;
        }
      }, epoch);
    }
    sync() {
      this._guard();
      if (!this.transport) return Promise.reject(new RecordsError("transport_unavailable"));
      if (this.syncing) return this.syncing;
      const epoch = this.generation;
      const run = async () => {
        try {
          await this._pull(epoch);
          for (let attempt = 0; attempt < 5000; attempt += 1) {
            this._guard(epoch);
            const operation = await this._change((state) => {
              const next = state.outbox.filter((op) => !state.records[op.record_id]?.conflict).sort((a, b) => a.order - b.order)[0];
              if (!next) return null;
              next.attempted = true; next.in_flight = true;
              return next;
            }, epoch);
            if (!operation) break;
            try {
              const result = await this.transport.mutate(clone(operation));
              this._guard(epoch);
              await this._ack(operation, result, epoch);
            } catch (error) {
              this._guard(epoch);
              await this._change((state) => {
                const op = state.outbox.find((item) => item.mutation_id === operation.mutation_id);
                if (op) op.in_flight = false;
                const record = state.records[operation.record_id];
                if (record && !record.conflict) { record.sync_state = "error"; record.last_error = error instanceof RecordsError ? error.code : "sync_failed"; }
              }, epoch);
              throw error instanceof RecordsError ? error : new RecordsError("sync_failed");
            }
          }
          await this._pull(epoch);
        } catch (error) { throw error instanceof RecordsError ? error : new RecordsError("sync_failed"); }
      };
      this.syncing = run().finally(() => { if (epoch === this.generation) this.syncing = null; });
      return this.syncing;
    }
    async exportBackup() {
      this._guard();
      const state=validateState(await this.store.read());
      this._guard();
      const records=Object.values(state.records).filter((record) => !record.deleted_at || record.conflict).map((record) => {
        const payload=projectPayload(record.conflict ? record.conflict.local : record);
        const draft=state.editor_drafts[record.id];
        if (draft) Object.assign(payload,{title:draft.title.trim() ? draft.title : payload.title,notes:draft.notes,status:draft.status});
        return payload;
      }).filter((record)=>record.url && record.title);
      return {schemaVersion:1, exportedAt:now(), records};
    }
    async importBackup(value) {
      const projects = validateBackup(value);
      const keys = new Map(await Promise.all(projects.map(async (project) => [project.canonical_url, await urlKey(project.canonical_url)])));
      return this._change((state) => {
        const activeCount = Object.values(state.records).filter((record) => !record.deleted_at).length;
        const existingKeys = new Set(Object.values(state.records).map((record) => record.canonical_url || record.local_canonical_url));
        if (activeCount + projects.filter((record) => !existingKeys.has(record.canonical_url)).length > MAX_RECORDS) fail("record_limit");
        let added = 0, conflicts = 0;
        for (const value of projects) {
          const existing = Object.values(state.records).find((record) => (record.canonical_url || record.local_canonical_url) === value.canonical_url || record.url_key === keys.get(value.canonical_url));
          if (existing) {
            if (existing.conflict || state.editor_drafts[existing.id]) fail("conflict_unresolved");
            if (existing.notes !== value.notes || existing.status !== value.status || existing.title !== value.title) {
              const priorState = clone(existing);
              existing.conflict = {kind:"import", remote:clone(existing), local:projectPayload(value),
                prior_state:priorState, prior_outbox:state.outbox.filter((op) => op.record_id === existing.id).map(clone)};
              Object.assign(existing, value, {sync_state:"conflict", updated_at:now()});
              state.outbox = state.outbox.filter((op) => op.record_id !== existing.id);
              conflicts += 1;
            }
          } else {
            const record = Object.assign({}, value, {id:newId(), url_key:keys.get(value.canonical_url), version:0, created_at:now(), updated_at:now(), deleted_at:null});
            state.records[record.id] = record;
            this._enqueue(state, record, "create", projectPayload(record), Boolean(value.notes || value.status !== "to_research"));
            added += 1;
          }
        }
        return {added, conflicts};
      });
    }
    stop() { this.stopped = true; this.generation += 1; if (typeof this.store.close === "function") this.store.close(); }
    async clearLocal() { this.stop(); await this.store.clear(); }
  }
  function toMarkdown(backup) {
    const records = validateBackup(backup);
    const slash = String.fromCharCode(92);
    const punctuation = new Set(Array.from("`*_{}[]()#+.!|<>-" + slash));
    const escape = (value) => Array.from(String(value), (character) => punctuation.has(character) ? slash + character : character).join("");
    const labels = {to_research:"待研究", tried:"已体验", watching:"重点关注"};
    return "# 我的项目\n\n" + records.map((record) => "## " + escape(record.title) + "\n\n<" + record.url.replace(/>/g, "%3E") + ">\n\n" + labels[record.status] + (record.source_issue_date ? " · " + record.source_issue_date : "") + "\n\n" + (record.notes ? record.notes.split("\n").map(escape).join("\n") + "\n\n" : "")).join("");
  }
  return Object.freeze({STATUSES, RecordsError, normalizeUrl, urlKey, validateProject, validateBackup,
    validateRemote, openStore, MemoryStore, Library, createSupabaseTransport, toMarkdown});
});
