/*
 * The 24" wall, in "shows the real app" mode.
 *
 * This page is just an iframe and a websocket. The kiosk tells the server
 * where to send the wall; the server relays it here as a "navigate" message,
 * and all this script does is point the iframe at that path. The outer page
 * and its websocket never reload on navigation — only the iframe's src does
 * — so a burst of kiosk taps doesn't cost a reconnect each time.
 */
(function (window, document) {
  "use strict";

  var WallLive = {
    socket: null,
    reconnectDelay: 1000,
    slug: document.body.getAttribute("data-display-slug") || "wall",
    frame: null,
    scrollRate: 0,
    scrollTimer: null
  };

  WallLive.init = function () {
    WallLive.frame = document.querySelector("[data-wall-frame]");
    WallLive.connect();
  };

  WallLive.connect = function () {
    if (!window.WebSocket) return;
    var scheme = window.location.protocol === "https:" ? "wss" : "ws";
    var url = scheme + "://" + window.location.host + "/ws/display/" + WallLive.slug + "/";

    try {
      WallLive.socket = new WebSocket(url);
    } catch (error) {
      return;
    }

    WallLive.socket.onopen = function () {
      WallLive.reconnectDelay = 1000;
      WallLive.setStatus(true);
      window.setInterval(function () {
        if (WallLive.socket.readyState === 1) {
          WallLive.socket.send(JSON.stringify({ type: "heartbeat" }));
        }
      }, 30000);
    };

    WallLive.socket.onmessage = function (event) {
      var data;
      try {
        data = JSON.parse(event.data);
      } catch (error) {
        return;
      }
      WallLive.handle(data);
    };

    WallLive.socket.onclose = function () {
      WallLive.setStatus(false);
      window.setTimeout(WallLive.connect, WallLive.reconnectDelay);
      WallLive.reconnectDelay = Math.min(WallLive.reconnectDelay * 2, 30000);
    };
  };

  WallLive.handle = function (data) {
    switch (data.type) {
      case "navigate":
        if (data.path && WallLive.frame) WallLive.frame.src = data.path;
        break;
      case "refresh":
        window.location.reload();
        break;
      case "scroll":
        WallLive.setScrollRate(data.rate);
        break;
      case "banner":
        WallLive.banner(data);
        break;
      default:
        break;
    }
  };

  /* Scrolling the wall (Story 51).
   *
   * The message carries a *rate*, not a position, because the control at the
   * other end is a spring-centred bend wheel: you push it and it returns to
   * centre. A position would need the panel to know how long the wall's page
   * is, which it has no way to find out — a rate needs nothing but the sign
   * and how hard.
   *
   * So the wall integrates it: one interval, scrolling by `rate` pixels a
   * tick until a rate of 0 arrives (the wheel springing back) or the socket
   * drops. The interval is torn down when idle rather than left spinning on
   * an always-on screen.
   *
   * It scrolls the *iframe's* document, not this shell — the shell is exactly
   * viewport-sized and never scrolls. Same-origin, so reaching into
   * contentWindow is allowed; it is wrapped anyway, because a cross-origin
   * page in there some day should stop the wall scrolling, not throw on every
   * tick forever.
   */
  WallLive.setScrollRate = function (rate) {
    var next = Number(rate) || 0;
    WallLive.scrollRate = Math.max(-120, Math.min(120, next));

    if (!WallLive.scrollRate) {
      if (WallLive.scrollTimer) {
        window.clearInterval(WallLive.scrollTimer);
        WallLive.scrollTimer = null;
      }
      return;
    }
    if (WallLive.scrollTimer) return;

    WallLive.scrollTimer = window.setInterval(function () {
      var frame = WallLive.frame;
      if (!frame || !WallLive.scrollRate) return;
      try {
        frame.contentWindow.scrollBy(0, WallLive.scrollRate);
      } catch (error) {
        WallLive.setScrollRate(0);   // not ours to scroll — stop trying
      }
    }, 50);
  };

  /* An alert takes over the top of the wall for a while, then hands it back.
     A critical one (hold_seconds 0) stays until something replaces it.

     This is the whole reason the "display" notification channel exists
     (nora_home/notifications/channels/display.py). The ambient wall this page
     replaced handled it; this one didn't, so every alert routed to the wall
     was accepted by the bus and then silently dropped in the browser. */
  WallLive.banner = function (data) {
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

    window.clearTimeout(WallLive.bannerTimer);
    var hold = data.hold_seconds;
    if (hold && hold > 0) {
      WallLive.bannerTimer = window.setTimeout(function () {
        banner.classList.remove("is-visible");
      }, hold * 1000);
    }
  };

  WallLive.setStatus = function (online) {
    var dot = document.querySelector("[data-wall-status]");
    if (dot) dot.classList.toggle("is-offline", !online);
  };

  document.addEventListener("DOMContentLoaded", WallLive.init);
  window.WallLive = WallLive;
})(window, document);
