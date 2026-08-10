/*
 * The 10.1" kiosk — the control desk (Story 50).
 *
 * It holds a websocket and sends commands; the server relays them to the wall.
 * Every key gives immediate visual feedback rather than waiting for the round
 * trip, because a touchscreen that does not respond in 100ms feels broken and
 * people press it twice.
 *
 * Two inputs, one vocabulary. The app scroller down the left is the shared
 * Picker component (assets/js/nh-picker.js), which only ever *picks* — it
 * dispatches `nh-pick` and leaves the meaning to the host page. Here a pick
 * means "swap the key bank and send the wall to that app's landing page". The
 * keys themselves are `navigate`. That is the whole desk, because navigate /
 * refresh / banner is everything wall-live.js implements.
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

    // The Picker bubbles this from .vsel; the desk turns it into a wall move.
    document.addEventListener("nh-pick", function (event) {
      Kiosk.selectApp(event.detail.slug);
    });

    document.addEventListener("click", function (event) {
      var key = event.target.closest("[data-kiosk-action]");
      if (!key || key.disabled) return;
      Kiosk.flash(key);

      var payload = {
        action: key.getAttribute("data-kiosk-action"),
        display: key.getAttribute("data-display") || Kiosk.target
      };
      if (key.hasAttribute("data-path")) payload.path = key.getAttribute("data-path");
      if (key.hasAttribute("data-delta")) payload.delta = key.getAttribute("data-delta");
      Kiosk.send(payload);
    });

    // `scroll` does not bubble, so this has to be the capture phase — the
    // same trap nh-picker.js documents for its own scroll listener.
    document.addEventListener("scroll", function (event) {
      if (event.target.hasAttribute && event.target.hasAttribute("data-desk-bank")) {
        Kiosk.updateBankLabel(event.target);
      }
    }, true);

    Kiosk.updateBankLabel(Kiosk.visibleBank());

    var desk = document.querySelector("[data-desk]");
    Kiosk.zoomMin = parseFloat(desk && desk.getAttribute("data-zoom-min")) || 0.8;
    Kiosk.zoomMax = parseFloat(desk && desk.getAttribute("data-zoom-max")) || 2.0;
    var shown = parseFloat(desk && desk.getAttribute("data-zoom"));
    if (!isNaN(shown)) Kiosk.showZoom(shown);
    var vol = parseFloat(desk && desk.getAttribute("data-volume"));
    if (!isNaN(vol)) Kiosk.showVolume(vol);
    Kiosk.wireBendWheel();

    // No accidental pinch-zoom or text selection on a wall-mounted panel.
    document.addEventListener("gesturestart", function (e) { e.preventDefault(); });
  };

  /* Swap which bank of keys is lit, update the readout, and send the wall to
     that app's landing page — the same thing tapping its first key would do. */
  Kiosk.selectApp = function (slug) {
    var chosen = null;
    document.querySelectorAll("[data-desk-bank]").forEach(function (bank) {
      var mine = bank.getAttribute("data-desk-bank") === slug;
      bank.hidden = !mine;
      if (mine) chosen = bank;
    });
    if (!chosen) return;

    var item = document.querySelector('.vsel-i[data-v="' + cssEscape(slug) + '"]');
    var title = item ? item.querySelector(".vsel-t").textContent.trim() : slug;
    Kiosk.setText("[data-desk-readout-value]", title);
    Kiosk.setText("[data-desk-app-title]", title);

    Kiosk.updateBankLabel(chosen);

    var first = chosen.querySelector("[data-path]");
    if (first) {
      Kiosk.send({ action: "navigate", display: Kiosk.target,
                   path: first.getAttribute("data-path") });
    }
  };

  /* "Bank n / m", derived from what actually overflows rather than hardcoded.
     The mockup draws this label as a fixed "Bank 1 / 1" — fine in a prototype
     with two apps, but a legend that cannot be wrong today and silently
     becomes wrong the first time an app declares a seventh control is the
     shape of bug this house keeps finding on its own screens. The bank
     scrolls (it is a touch panel), so a "page" is one screenful. */
  Kiosk.updateBankLabel = function (bank) {
    var label = document.querySelector("[data-desk-bank-count]");
    if (!label || !bank) return;
    var pages = Math.max(1, Math.ceil(bank.scrollHeight / bank.clientHeight));
    // Across the scrollable *range*, not in clientHeight steps. The obvious
    // `floor(scrollTop / clientHeight) + 1` can never reach the last page:
    // scrollTop maxes out at scrollHeight - clientHeight, so with two pages
    // it tops out around 0.45 of a page and the legend sticks at "1 / 2".
    // Caught by scrolling a deliberately overflowed bank to the bottom.
    var range = bank.scrollHeight - bank.clientHeight;
    var page = (pages === 1 || range <= 0) ? 1
      : 1 + Math.round((bank.scrollTop / range) * (pages - 1));
    label.textContent = "Bank " + page + " / " + pages;
  };

  Kiosk.visibleBank = function () {
    return document.querySelector("[data-desk-bank]:not([hidden])");
  };

  /* Paint the zoom fader from a value the server confirmed. */
  Kiosk.showZoom = function (value) {
    var readout = document.querySelector("[data-desk-zoom-value]");
    var fill = document.querySelector("[data-desk-zoom-fill]");
    var cap = document.querySelector("[data-desk-zoom-cap]");
    if (readout) readout.textContent = value.toFixed(2) + "\u00d7";

    var min = Kiosk.zoomMin, max = Kiosk.zoomMax;
    var pct = Math.max(0, Math.min(1, (value - min) / (max - min)));
    // The cap is 26px wide and the groove is inset 12px each side, so the
    // travel is (100% - 24px) — matching .slot's own geometry in
    // components.css rather than assuming the track is the full width.
    if (fill) fill.style.width = "calc((100% - 24px) * " + pct.toFixed(4) + ")";
    if (cap) cap.style.left = "calc(12px + (100% - 24px) * " + pct.toFixed(4) + ")";
  };

  /* Same shape as showZoom, against 0-100 rather than the zoom bounds. */
  Kiosk.showVolume = function (level) {
    var readout = document.querySelector("[data-desk-volume-value]");
    var fill = document.querySelector("[data-desk-volume-fill]");
    var cap = document.querySelector("[data-desk-volume-cap]");
    if (readout) readout.textContent = level + "%";

    var pct = Math.max(0, Math.min(1, level / 100));
    if (fill) fill.style.width = "calc((100% - 24px) * " + pct.toFixed(4) + ")";
    if (cap) cap.style.left = "calc(12px + (100% - 24px) * " + pct.toFixed(4) + ")";
  };

  /* The bend wheel. Spring-centred: it sends a scroll *rate* while held and
     0 the moment it is let go, so the wall stops. Pointer events cover mouse
     and touch with one path, and setPointerCapture is what makes dragging off
     the wheel still deliver the release — without it, letting go outside the
     control leaves the wall scrolling forever. */
  Kiosk.wireBendWheel = function () {
    var bend = document.querySelector("[data-desk-bend]");
    var wheel = document.querySelector("[data-desk-wheel]");
    if (!bend) return;

    var active = false;

    function rateFrom(event) {
      var box = bend.getBoundingClientRect();
      var middle = box.top + box.height / 2;
      // -1 at the top of the wheel, +1 at the bottom, 0 at the detent.
      var offset = (event.clientY - middle) / (box.height / 2);
      return Math.max(-1, Math.min(1, offset));
    }

    function apply(offset) {
      if (wheel) wheel.style.transform = "translateY(" + (offset * 26).toFixed(1) + "px)";
      bend.setAttribute("aria-valuenow", offset.toFixed(2));
      // Pixels per 50ms tick on the wall. 26 is brisk without being
      // unreadable; the wall clamps it again at its own end.
      Kiosk.send({ action: "scroll", display: Kiosk.target,
                   rate: Math.round(offset * 26) });
    }

    bend.addEventListener("pointerdown", function (event) {
      active = true;
      bend.classList.add("held");
      // Capture is a nicety — it makes releasing *off* the wheel still deliver
      // the stop. It is not allowed to cost us the actual press: it throws
      // InvalidStateError for a pointer the UA no longer considers active, and
      // with it before apply() a throw meant the wheel lit up and then did
      // nothing at all. Seen on the panel: the .held glow appeared, the wheel
      // never moved, and no scroll was ever sent.
      try {
        bend.setPointerCapture(event.pointerId);
      } catch (error) {
        /* release still arrives via pointerup on the element itself */
      }
      apply(rateFrom(event));
    });
    bend.addEventListener("pointermove", function (event) {
      if (active) apply(rateFrom(event));
    });
    function release() {
      if (!active) return;
      active = false;
      bend.classList.remove("held");
      if (wheel) wheel.style.transform = "";
      bend.setAttribute("aria-valuenow", "0");
      Kiosk.send({ action: "scroll", display: Kiosk.target, rate: 0 });
    }

    // On the element *and* on the window: if setPointerCapture was refused,
    // a release outside the wheel would otherwise never arrive and the wall
    // would scroll forever. `release` is idempotent, so hearing it twice is
    // harmless.
    ["pointerup", "pointercancel"].forEach(function (name) {
      bend.addEventListener(name, release);
      window.addEventListener(name, release);
    });
  };

  Kiosk.setText = function (selector, text) {
    var el = document.querySelector(selector);
    if (el) el.textContent = text;
  };

  Kiosk.flash = function (key) {
    key.classList.add("is-pressed");
    window.setTimeout(function () { key.classList.remove("is-pressed"); }, 180);
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
      // The server clamps zoom, so the desk shows what was actually stored
      // rather than what it asked for — press "+" at the ceiling and the
      // readout should simply stop moving.
      if (data.type === "ack" && typeof data.zoom === "number") Kiosk.showZoom(data.zoom);
      if (data.type === "ack" && typeof data.volume === "number") Kiosk.showVolume(data.volume);
      // `./nora screens` broadcasts {type:"refresh"} to every connected screen
      // after a deploy. wall-live.js has always honoured it; this file never
      // did, so the kiosk silently kept its old markup while the wall updated
      // — and `nora`'s own comment claimed both screens handled it. Found on
      // the physical panel deploying Story 47: it kept an eight-tile render
      // with a since-deleted tile on it, and only `./nora screens relaunch`
      // (a full Chromium restart) ever picked the change up.
      if (data.type === "refresh") window.location.reload();
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
    // Socket down: fall back to the HTTP command endpoint so the keys still
    // work. The /home/ prefix matters — the platform is mounted there (see
    // config/urls.py), and without it every fallback 404'd and surfaced as
    // "Couldn't reach the wall display." That is exactly what the kiosk was
    // showing on the physical panel on 2026-08-04.
    if (window.NoraHome && window.NoraHome.post) {
      window.NoraHome.post("/home/displays/command/" + payload.display + "/", payload)
        .catch(function () { Kiosk.toast("Couldn't reach the wall display."); });
    }
  };

  /* The link lamp. Starts linked and only ever goes lost — if this socket
     drops, every key on the panel is dead, so it is worth saying plainly
     rather than leaving someone pressing keys that go nowhere. */
  Kiosk.setStatus = function (online) {
    var lamp = document.querySelector("[data-desk-lamp]");
    if (!lamp) return;
    lamp.classList.toggle("lost", !online);
    Kiosk.setText("[data-desk-lamp-text]", online ? "Linked to wall" : "Wall unreachable");
  };

  Kiosk.toast = function (message) {
    var toast = document.querySelector("[data-kiosk-toast]");
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add("is-visible");
    window.setTimeout(function () { toast.classList.remove("is-visible"); }, 3200);
  };

  function cssEscape(value) {
    return window.CSS && window.CSS.escape ? window.CSS.escape(value)
                                           : String(value).replace(/"/g, '\\"');
  }

  document.addEventListener("DOMContentLoaded", Kiosk.init);
  window.Kiosk = Kiosk;
})(window, document);
