/*
 * The 10.1" kiosk controller.
 *
 * It holds a websocket and sends commands; the server relays them to the wall. Every
 * button gives immediate visual feedback rather than waiting for the round trip,
 * because a touchscreen that does not respond in 100ms feels broken and people
 * press it twice.
 */
(function (window, document) {
  "use strict";

  var Kiosk = {
    socket: null,
    reconnectDelay: 1000,
    target: document.body.getAttribute("data-target-display") || "wall"
  };

  Kiosk.init = function () {
    Kiosk.connect();

    document.addEventListener("click", function (event) {
      var button = event.target.closest("[data-kiosk-action]");
      if (!button) return;
      var action = button.getAttribute("data-kiosk-action");
      Kiosk.flash(button);

      // "switch-app" and "show-menu" are local-only: they swap which set of
      // buttons this screen shows, they don't mean anything to the server.
      // "switch-app" also tells the wall to go to that app's landing page,
      // same as a plain "navigate" tap would.
      if (action === "show-menu") {
        Kiosk.showScreen("menu");
        return;
      }
      if (action === "switch-app") {
        Kiosk.showScreen("app:" + button.getAttribute("data-app"));
        Kiosk.send({
          action: "navigate",
          display: button.getAttribute("data-display") || Kiosk.target,
          path: button.getAttribute("data-path")
        });
        return;
      }

      var payload = {
        action: action,
        display: button.getAttribute("data-display") || Kiosk.target
      };
      if (button.hasAttribute("data-path")) {
        payload.path = button.getAttribute("data-path");
      }
      Kiosk.send(payload);
    });

    // No accidental pinch-zoom or text selection on a wall-mounted panel.
    document.addEventListener("gesturestart", function (e) { e.preventDefault(); });
  };

  Kiosk.showScreen = function (name) {
    document.querySelectorAll("[data-kiosk-screen]").forEach(function (screen) {
      screen.hidden = screen.getAttribute("data-kiosk-screen") !== name;
    });
  };

  Kiosk.flash = function (button) {
    button.classList.add("is-pressed");
    window.setTimeout(function () { button.classList.remove("is-pressed"); }, 180);
  };

  Kiosk.connect = function () {
    if (!window.WebSocket) return;
    var scheme = window.location.protocol === "https:" ? "wss" : "ws";

    try {
      Kiosk.socket = new WebSocket(scheme + "://" + window.location.host + "/ws/kiosk/");
    } catch (error) {
      return;
    }

    Kiosk.socket.onopen = function () {
      Kiosk.reconnectDelay = 1000;
      Kiosk.setStatus(true);
      window.setInterval(function () {
        if (Kiosk.socket.readyState === 1) {
          Kiosk.socket.send(JSON.stringify({ type: "heartbeat" }));
        }
      }, 30000);
    };

    Kiosk.socket.onmessage = function (event) {
      var data;
      try {
        data = JSON.parse(event.data);
      } catch (error) {
        return;
      }
      if (data.type === "error") Kiosk.toast(data.message);
    };

    Kiosk.socket.onclose = function () {
      Kiosk.setStatus(false);
      window.setTimeout(Kiosk.connect, Kiosk.reconnectDelay);
      Kiosk.reconnectDelay = Math.min(Kiosk.reconnectDelay * 2, 20000);
    };
  };

  Kiosk.send = function (payload) {
    if (Kiosk.socket && Kiosk.socket.readyState === 1) {
      Kiosk.socket.send(JSON.stringify(payload));
      return;
    }
    // Socket down: fall back to the HTTP command endpoint so the buttons still
    // work. The /home/ prefix matters — the platform is mounted there (see
    // config/urls.py), and without it every fallback 404'd and surfaced as
    // "Couldn't reach the wall display." That is exactly what the kiosk was
    // showing on the physical panel on 2026-08-04.
    if (window.NoraHome && window.NoraHome.post) {
      window.NoraHome.post("/home/displays/command/" + payload.display + "/", payload)
        .catch(function () { Kiosk.toast("Couldn't reach the wall display."); });
    }
  };

  Kiosk.setStatus = function (online) {
    var dot = document.querySelector("[data-kiosk-status]");
    if (dot) dot.classList.toggle("is-offline", !online);
  };

  Kiosk.toast = function (message) {
    var toast = document.querySelector("[data-kiosk-toast]");
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add("is-visible");
    window.setTimeout(function () { toast.classList.remove("is-visible"); }, 3200);
  };

  document.addEventListener("DOMContentLoaded", Kiosk.init);
  window.Kiosk = Kiosk;
})(window, document);
