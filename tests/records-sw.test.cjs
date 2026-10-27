"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function fixture(options = {}) {
  const handlers = new Map(), stored = new Map(), seen = [];
  const cache = {
    async addAll(urls) { seen.push(["install", urls]); },
    async put(request, response) { if (options.quota) throw new Error("synthetic quota"); stored.set(request.url, response); },
    async match(request, query) { const url = typeof request === "string" ? request : request.url; return stored.get(query && query.ignoreSearch ? url.split("?")[0] : url); }
  };
  const context = {
    URL, Request, Response, Set,
    self: {registration: {scope: "https://library.example/xait/"},
      addEventListener: (name, fn) => handlers.set(name, fn),
      skipWaiting: async () => {}, clients: {claim: async () => {}}},
    caches: {open: async () => { if (options.noCache) throw new Error("synthetic storage"); return cache; }, keys: async () => [], delete: async () => true},
    fetch: async (request) => {
      seen.push(["network", request.url]);
      if (options.offline) throw new Error("synthetic offline");
      return {ok: true, type: "basic", headers: new Headers(), clone() { return this; }, marker: "network"};
    }
  };
  const source = fs.readFileSync(path.join(__dirname, "../site/sw.js"), "utf8")
    .replace("__PUBLIC_ASSETS__", JSON.stringify(["assets/app.js", "assets/records-core.js"]));
  vm.runInNewContext(source, context);
  async function fetchEvent(url, init) {
    let response;
    handlers.get("fetch")({request: new Request(url, init), respondWith(value) { response = value; }});
    return response ? await response : null;
  }
  return {handlers, stored, seen, fetchEvent};
}

test("authentication, private APIs and foreign requests never enter public cache", async () => {
  const f = fixture();
  for (const [url, init] of [
    ["https://library.example/xait/?code=synthetic"],
    ["https://library.example/xait/?provider_token=synthetic"],
    ["https://library.example/xait/?other=private"],
    ["https://library.example/xait/private.json"],
    ["https://library.example/xait/", {headers: {Authorization: "synthetic"}}],
    ["https://cloud.example/rest/v1/rpc/list_my_records"],
    ["https://library.example/other/assets/app.js"],
    ["https://library.example/xait/", {method: "POST"}]
  ]) assert.equal(await f.fetchEvent(url, init), null);
  assert.equal(f.seen.length, 0);
});

test("network response wins and a cache write failure cannot break reading", async () => {
  for (const options of [{quota: true}, {noCache: true}, {}]) {
    const f = fixture(options);
    assert.equal((await f.fetchEvent("https://library.example/xait/?lang=en")).marker, "network");
    assert.equal(f.seen[0][0], "network");
  }
});

test("offline public shell fallback uses only previously cached public content", async () => {
  const f = fixture({offline: true});
  f.stored.set("https://library.example/xait/", {marker: "public-shell"});
  assert.equal((await f.fetchEvent("https://library.example/xait/?lang=zh")).marker, "public-shell");
  assert.equal(await f.fetchEvent("https://library.example/xait/?code=synthetic"), null);
});

test("install precaches only clean homepage and declared static assets", async () => {
  const f = fixture();
  let work;
  f.handlers.get("install")({waitUntil(value) {work = value;}});
  await work;
  assert.deepEqual(Array.from(f.seen[0][1]), ["https://library.example/xait/", "https://library.example/xait/assets/app.js", "https://library.example/xait/assets/records-core.js"]);
});
