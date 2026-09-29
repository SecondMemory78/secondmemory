/* Поведение страниц сайта. Всё, что тут есть, — три мелочи:
   тень у шапки при прокрутке, появление блоков и подстановка иконок.
   Никаких библиотек: страница статическая, React ей не нужен. */
(function () {
  "use strict";

  // ── иконки ────────────────────────────────────────────────────────────────
  // Раскладываются по атрибуту data-ic, чтобы не засорять разметку SVG.
  var S = 'xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" ' +
          'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"';
  var ICONS = {
    brain: '<svg ' + S + '><path d="M12 5a3 3 0 0 0-3 3c-1.7.6-3 1.9-3 3.9 0 2.5 2.1 4.6 4.7 4.6H14c2.6 0 4.7-2.1 4.7-4.6 0-2-1.3-3.3-3-3.9A3 3 0 0 0 12 5Z"/></svg>',
    play: '<svg ' + S + '><path d="M8 5.5v13l10-6.5-10-6.5Z"/></svg>',
    arrowDown: '<svg ' + S + '><path d="M12 5v14M6 13l6 6 6-6"/></svg>',
    arrowRight: '<svg ' + S + '><path d="M5 12h14M13 6l6 6-6 6"/></svg>',
    telegram: '<svg ' + S + '><path d="M21 4 3 11l5 2 2 6 3-4 5 4 3-15Z"/><path d="m8 13 10-7-6 9"/></svg>',
    trendingUp: '<svg ' + S + '><path d="M3 17 9 11l4 4 8-8"/><path d="M15 7h6v6"/></svg>',
    list: '<svg ' + S + '><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/></svg>',
    camera: '<svg ' + S + '><path d="M4 8h3l2-2h6l2 2h3v11H4V8Z"/><circle cx="12" cy="13" r="3.5"/></svg>',
    template: '<svg ' + S + '><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M9 9v11"/></svg>',
    shield: '<svg ' + S + '><path d="M12 3 5 6v6c0 4 3 7.3 7 9 4-1.7 7-5 7-9V6l-7-3Z"/><path d="m9 12 2 2 4-4"/></svg>',
    search: '<svg ' + S + '><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>',
    history: '<svg ' + S + '><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/><path d="M12 7v5l3 2"/></svg>',
    download: '<svg ' + S + '><path d="M12 4v11M7 11l5 5 5-5"/><path d="M4 20h16"/></svg>',
    signature: '<svg ' + S + '><path d="M3 18c3 0 4-9 7-9s2 7 4 7 2-4 4-4 2 2 3 2"/><path d="M4 21h16"/></svg>',
    check: '<svg ' + S + '><path d="m5 12 5 5 9-10"/></svg>',
    server: '<svg ' + S + '><rect x="3" y="4" width="18" height="7" rx="2"/><rect x="3" y="13" width="18" height="7" rx="2"/><path d="M7 7.5h.01M7 16.5h.01"/></svg>',
    users: '<svg ' + S + '><circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c0-3.6 2.9-6 6.5-6s6.5 2.4 6.5 6"/><path d="M17 8.5a3 3 0 0 0 0-1M17.5 14.5c2.4.5 4 2.5 4 5.5"/></svg>',
    chart: '<svg ' + S + '><path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/></svg>',
    code: '<svg ' + S + '><path d="m8 8-5 4 5 4M16 8l5 4-5 4M14 5l-4 14"/></svg>',
  };

  function icons() {
    var nodes = document.querySelectorAll("[data-ic]");
    for (var i = 0; i < nodes.length; i++) {
      var name = nodes[i].getAttribute("data-ic");
      if (ICONS[name]) nodes[i].innerHTML = ICONS[name];
    }
  }

  // ── тень у шапки ──────────────────────────────────────────────────────────
  function nav() {
    var n = document.querySelector(".nav");
    if (!n) return;
    var onScroll = function () { n.classList.toggle("scrolled", window.scrollY > 8); };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
  }

  // ── появление блоков ──────────────────────────────────────────────────────
  // Уважаем «уменьшить движение»: если человек попросил без анимаций —
  // показываем всё сразу, а не прячем контент за неработающим переходом.
  function reveal() {
    var items = document.querySelectorAll(".rv");
    var still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (still || !("IntersectionObserver" in window)) {
      for (var i = 0; i < items.length; i++) items[i].classList.add("in");
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
      });
    }, { rootMargin: "0px 0px -10% 0px", threshold: 0.05 });
    for (var j = 0; j < items.length; j++) {
      items[j].style.transitionDelay = (j % 4) * 70 + "ms";
      io.observe(items[j]);
    }
  }

  function start() { icons(); nav(); reveal(); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
