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
    frame: null
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
      default:
        break;
    }
  };

  WallLive.setStatus = function (online) {
    var dot = document.querySelector("[data-wall-status]");
    if (dot) dot.classList.toggle("is-offline", !online);
  };

  document.addEventListener("DOMContentLoaded", WallLive.init);
  window.WallLive = WallLive;
})(window, document);
