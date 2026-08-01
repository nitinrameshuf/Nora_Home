/*
 * The always-on 24" display.
 *
 * Every panel is rendered into the page once and switched client-side, so a
 * rotation costs nothing and a network blip never blanks the wall. Rotation itself
 * is server-driven (a Celery beat task sends "next"), which is what lets the kiosk
 * pin a panel and have the wall actually obey.
 *
 * If the socket dies, a local timer takes over so the screen keeps moving until the
 * server comes back.
 */
(function (window, document) {
  "use strict";

  var Wall = {
    panels: [],
    index: 0,
    socket: null,
    localTimer: null,
    reconnectDelay: 1000,
    slug: document.body.getAttribute("data-display-slug") || "wall",
    rotationSeconds: parseInt(document.body.getAttribute("data-rotation") || "45", 10),
    pinnedUntil: 0
  };

  Wall.init = function () {
    Wall.panels = Array.prototype.slice.call(
      document.querySelectorAll("[data-panel-key]")
    );
    if (!Wall.panels.length) return;

    Wall.show(0);
    Wall.connect();
    Wall.startLocalTimer();
    Wall.startClock();

    // Screens burn in. A slow pixel shift over the hour costs nothing and buys
    // years on an always-on panel.
    window.setInterval(Wall.shift, 300000);
  };

  Wall.show = function (index) {
    if (!Wall.panels.length) return;
    Wall.index = ((index % Wall.panels.length) + Wall.panels.length) % Wall.panels.length;
    Wall.panels.forEach(function (panel, i) {
      var active = i === Wall.index;
      panel.hidden = !active;
      panel.setAttribute("aria-hidden", active ? "false" : "true");
    });
    Wall.updateDots();
  };

  Wall.showByKey = function (key) {
    for (var i = 0; i < Wall.panels.length; i += 1) {
      if (Wall.panels[i].getAttribute("data-panel-key") === key) {
        Wall.show(i);
        return true;
      }
    }
    return false;
  };

  Wall.next = function () {
    if (Date.now() < Wall.pinnedUntil) return;
    Wall.show(Wall.index + 1);
  };

  Wall.updateDots = function () {
    var dots = document.querySelectorAll("[data-panel-dot]");
    Array.prototype.forEach.call(dots, function (dot, i) {
      dot.classList.toggle("is-active", i === Wall.index);
    });
  };

  Wall.shift = function () {
    var stage = document.querySelector(".wall-stage");
    if (!stage) return;
    var dx = Math.round(Math.random() * 8) - 4;
    var dy = Math.round(Math.random() * 8) - 4;
    stage.style.transform = "translate(" + dx + "px," + dy + "px)";
  };

  Wall.startClock = function () {
    var clock = document.querySelector("[data-wall-clock]");
    var dateEl = document.querySelector("[data-wall-date]");
    if (!clock) return;

    function tick() {
      var now = new Date();
      clock.textContent = now.toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit"
      });
      if (dateEl) {
        dateEl.textContent = now.toLocaleDateString([], {
          weekday: "long",
          day: "numeric",
          month: "long"
        });
      }
    }
    tick();
    window.setInterval(tick, 10000);
  };

  /* Local fallback rotation — only fires when the server has gone quiet. */
  Wall.startLocalTimer = function () {
    window.clearInterval(Wall.localTimer);
    Wall.localTimer = window.setInterval(function () {
      if (Wall.socket && Wall.socket.readyState === 1) return;
      Wall.next();
    }, Wall.rotationSeconds * 1000);
  };

  Wall.connect = function () {
    if (!window.WebSocket) return;
    var scheme = window.location.protocol === "https:" ? "wss" : "ws";
    var url = scheme + "://" + window.location.host + "/ws/display/" + Wall.slug + "/";

    try {
      Wall.socket = new WebSocket(url);
    } catch (error) {
      return;
    }

    Wall.socket.onopen = function () {
      Wall.reconnectDelay = 1000;
      Wall.setStatus(true);
      window.setInterval(function () {
        if (Wall.socket.readyState === 1) {
          Wall.socket.send(JSON.stringify({ type: "heartbeat" }));
        }
      }, 30000);
    };

    Wall.socket.onmessage = function (event) {
      var data;
      try {
        data = JSON.parse(event.data);
      } catch (error) {
        return;
      }
      Wall.handle(data);
    };

    Wall.socket.onclose = function () {
      Wall.setStatus(false);
      window.setTimeout(Wall.connect, Wall.reconnectDelay);
      Wall.reconnectDelay = Math.min(Wall.reconnectDelay * 2, 30000);
    };
  };

  Wall.handle = function (data) {
    switch (data.type) {
      case "welcome":
        if (data.panel) Wall.showByKey(data.panel);
        if (data.night_mode) Wall.setNight(true);
        break;
      case "show":
        if (Wall.showByKey(data.panel) && data.pin_seconds) {
          Wall.pinnedUntil = Date.now() + data.pin_seconds * 1000;
        }
        break;
      case "next":
        Wall.next();
        break;
      case "previous":
        Wall.show(Wall.index - 1);
        break;
      case "unpin":
        Wall.pinnedUntil = 0;
        break;
      case "banner":
        Wall.banner(data);
        break;
      case "night":
        Wall.setNight(true);
        break;
      case "wake":
        Wall.setNight(false);
        break;
      case "refresh":
        window.location.reload();
        break;
      default:
        break;
    }
  };

  Wall.setNight = function (on) {
    document.body.classList.toggle("night-dim", !!on);
  };

  Wall.setStatus = function (online) {
    var dot = document.querySelector("[data-wall-status]");
    if (dot) dot.classList.toggle("is-offline", !online);
  };

  /* An alert takes over the wall for a while, then hands it back. A critical one
     holds until someone acknowledges it. */
  Wall.banner = function (data) {
    var banner = document.querySelector("[data-wall-banner]");
    if (!banner) return;

    banner.className = "wall-banner is-visible severity-" + (data.severity || "info");
    banner.innerHTML = "";

    var title = document.createElement("div");
    title.className = "wall-banner__title";
    title.textContent = data.title || "";
    banner.appendChild(title);

    if (data.body) {
      var body = document.createElement("div");
      body.className = "wall-banner__body";
      body.textContent = data.body;
      banner.appendChild(body);
    }
    if (data.recipient) {
      var who = document.createElement("div");
      who.className = "wall-banner__who";
      who.textContent = data.recipient;
      banner.appendChild(who);
    }

    var hold = data.hold_seconds;
    if (hold && hold > 0) {
      window.setTimeout(function () {
        banner.classList.remove("is-visible");
      }, hold * 1000);
    }
  };

  document.addEventListener("DOMContentLoaded", Wall.init);
  window.Wall = Wall;
})(window, document);
