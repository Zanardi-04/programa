/* Cache exclusivo desta instalação; sem redes externas. */
'use strict';
const CACHE = 'rumo-ao-milhao-static-v1-4-20261030';
const ASSETS = ['./','./index.html','./styles.css','./app.js','./import.js','./manifest.webmanifest','./icon-192.png','./icon-512.png','./apple-touch-icon.png'];
self.addEventListener('install',event=>{
  event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(ASSETS)).then(()=>self.skipWaiting()));
});
self.addEventListener('activate',event=>{
  event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('rumo-ao-milhao-static-')&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));
});
self.addEventListener('fetch',event=>{
  if(event.request.method!=='GET'||new URL(event.request.url).origin!==self.location.origin)return;
  if(!new URL(event.request.url).pathname.startsWith(new URL(self.registration.scope).pathname))return;
  // Primeiro busca a versão nova quando houver internet; usa cache se estiver offline.
  event.respondWith(fetch(event.request).then(response=>{
    if(response.ok&&response.type==='basic') {const copy=response.clone();event.waitUntil(caches.open(CACHE).then(cache=>cache.put(event.request,copy)));}
    return response;
  }).catch(async()=>{
    const cached=await caches.match(event.request,{ignoreSearch:true});
    return cached||(event.request.mode==='navigate'?await caches.match('./index.html'):Response.error());
  }));
});
