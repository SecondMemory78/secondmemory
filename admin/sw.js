// Service worker админ-панели.
//
// Зачем свой, а не общий с приложением. Админка лежит в /admin/, а регистрировала
// service worker приложения по корневому /sw.js. В сборке этот файл есть только
// в /app/sw.js, поэтому в корне отдавалась 404 и подписка не работала — на
// сервере пришлось городить отдачу /sw.js из корня средствами nginx.
//
// Хуже другое: тот воркер строит ссылки от собственной области видимости. При
// регистрации из корня область — «/», и клик по уведомлению уводил на
// https://домен/notifications, то есть на сайт-витрину, а не в админку.
//
// Свой воркер в /admin/ получает область «/admin/» и открывает админку.

self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) { data = {}; }

  const title = data.title || "Вторая память — админка";
  const options = {
    body: data.body || "",
    icon: new URL("icon-192.png", self.registration.scope).href,
    badge: new URL("badge-96.png", self.registration.scope).href,
    tag: data.tag || "admin",
    data: { url: data.url || self.registration.scope },   // область = /admin/
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || self.registration.scope;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
      // если админка уже открыта — переводим фокус на неё, а не плодим вкладки
      for (const c of list) {
        if (c.url.includes("/admin") && "focus" in c) return c.focus();
      }
      return self.clients.openWindow(url);
    })
  );
});

// Забираем управление сразу, не дожидаясь перезагрузки страницы.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
