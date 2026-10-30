/* Public shell only. Private records live in the account-isolated IndexedDB. */
"use strict";
const CACHE = "xait-public-44d7475cc505b7fd3549cc69";
const ASSETS = ["assets/app.css", "assets/app.js", "assets/records.css", "assets/records-core.js", "assets/records-ui.js", "assets/vendor/supabase-2.118.0.js", "assets/vendor/SUPABASE-LICENSE.txt"];
const AUTH_FIELDS = new Set(["code", "access_token", "refresh_token", "error", "error_description", "error_code"]);
const base = () => new URL(self.registration.scope);
const publicRequest = (request) => {
  if (request.method !== "GET" || request.headers.has("Authorization")) return false;
  const url = new URL(request.url);
  const root = base();
  if (url.origin !== root.origin || !url.pathname.startsWith(root.pathname)) return false;
  if ([...url.searchParams.keys()].some((key) => AUTH_FIELDS.has(key))) return false;
  if ([...url.searchParams.keys()].some((key) => key !== "lang")) return false;
  const path = url.pathname.slice(root.pathname.length);
  return path === "" || path === "index.html" || ASSETS.includes(path) ||
    /^archive\/[0-9]{4}-[0-9]{2}-[0-9]{2}\/(?:index\.html)?$/.test(path);
};
self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    const root = base();
    const targets = [new URL("./", root).href, ...ASSETS.map((path) => new URL(path, root).href)];
    await cache.addAll(targets);
    await self.skipWaiting();
  })());
});
self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    for (const name of await caches.keys()) {
      if (name.startsWith("xait-public-") && name !== CACHE) await caches.delete(name);
    }
    await self.clients.claim();
  })());
});
self.addEventListener("fetch", (event) => {
  if (!publicRequest(event.request)) return;
  event.respondWith((async () => {
    let cache = null;
    try { cache = await caches.open(CACHE); } catch (_) { /* Network reading still works without a cache. */ }
    try {
      const response = await fetch(event.request);
      if (cache && response.ok && response.type === "basic" && !response.headers.has("Set-Cookie")) {
        try { await cache.put(event.request, response.clone()); } catch (_) { /* Quota is not a reading failure. */ }
      }
      return response;
    } catch (_) {
      if (!cache) return Response.error();
      const response = await cache.match(event.request, {ignoreSearch: true});
      if (response) return response;
      if (event.request.mode === "navigate") {
        const shell = await cache.match(new URL("./", base()).href);
        if (shell) return shell;
      }
      return Response.error();
    }
  })());
});
