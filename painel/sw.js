// Guarda o painel no tablet para abrir mesmo sem internet.
const CACHE = "painel-eco-moedor-v1";
const ARQUIVOS = ["./", "index.html", "manifest.webmanifest", "logo.png", "icone-192.png", "icone-512.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ARQUIVOS)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
// Usa a versão salva na hora e atualiza em segundo plano quando houver internet.
self.addEventListener("fetch", e => {
  if (e.request.method !== "GET") return;
  e.respondWith(caches.open(CACHE).then(async c => {
    const salvo = await c.match(e.request);
    const rede = fetch(e.request).then(r => { if (r && (r.ok || r.type === "opaque")) c.put(e.request, r.clone()); return r; }).catch(() => salvo);
    return salvo || rede;
  }));
});
