/*
 * NoraHome — the bot, client side.
 *
 * She wanders when idle, slides toward whatever the user just touched, and
 * speaks when the server has something to say. Always on the ground, in the
 * bottom strip of the screen — she never climbs up into the content, just
 * left and right. No framework, no build step: this file is served straight
 * off the Pi and has to keep working when npm does not exist.
 *
 * Public API (house apps may call these):
 *     NoraHome.say("Nice work.", { mood: "proud" })
 *     NoraHome.react("celebrate")
 *     NoraHome.moveTo(x)             // viewport pixels; vertical position is
 *                                    // always the bottom strip, not settable
 *     NoraHome.goTo(element)         // slide beside an element, same strip
 */
(function (window, document) {
  "use strict";

  var REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var IDLE_WANDER_MS = 9000;
  var MARGIN = 24;
  var GROUND_MARGIN = 28; // how far above the very bottom edge the strip sits

  // nh-app.js (loaded first, see base.html) already put post()/csrfToken()
  // on window.NoraHome — this has to extend that same object, not replace
  // it. It used to do `window.NoraHome = NoraHome` at the bottom of this
  // file, which silently wiped both of those out on every page that loads
  // the bot, breaking anything that used them — the widget picker's save
  // request among them, which needs csrfToken() for its CSRF header and
  // was failing its POST with a 403 that nothing surfaced.
  var NoraHome = window.NoraHome = window.NoraHome || {};
  NoraHome.el = null;
  NoraHome.bubble = null;
  NoraHome.socket = null;
  NoraHome.idleTimer = null;
  NoraHome.bubbleTimer = null;
  NoraHome.reconnectDelay = 1000;
  NoraHome.position = { x: 0, y: 0 };
  NoraHome.enabled = true;

  /* ── Construction ───────────────────────────────────────────────────────── */
  NoraHome.mount = function () {
    if (document.querySelector(".nh-bot")) return;

    var bot = document.createElement("div");
    bot.className = "nh-bot";
    bot.setAttribute("data-mood", "idle");
    bot.setAttribute("role", "button");
    bot.setAttribute("tabindex", "0");
    bot.setAttribute("aria-label", "Nora Home. Press to say hello.");
    bot.innerHTML =
      '<div class="nh-bot__body">' +
      '<div class="nh-bot__mast">' +
      '<div class="nh-bot__head">' +
      '<div class="nh-bot__eyes">' +
      '<span class="nh-bot__eye"></span><span class="nh-bot__eye"></span>' +
      "</div>" +
      '<div class="nh-bot__dish"></div>' +
      "</div>" +
      "</div>" +
      '<div class="nh-bot__chassis"></div>' +
      '<div class="nh-bot__wheels">' +
      '<span class="nh-bot__wheel"></span><span class="nh-bot__wheel"></span>' +
      '<span class="nh-bot__wheel"></span>' +
      "</div>" +
      "</div>";

    var bubble = document.createElement("div");
    bubble.className = "nh-bubble";
    bubble.setAttribute("role", "status");
    bubble.setAttribute("aria-live", "polite");

    document.body.appendChild(bot);
    document.body.appendChild(bubble);
    NoraHome.el = bot;
    NoraHome.bubble = bubble;

    // Every button that navigates reloads the page in this multi-page app,
    // so mount() runs fresh each time — without this, the CSS transition
    // (meant for later moves) would also animate this very first
    // positioning, reading as a slide in from the CSS default (top-left)
    // to wherever she actually belongs, on every single navigation.
    bot.style.transition = "none";
    NoraHome.moveTo(window.innerWidth - 110);
    void bot.offsetWidth; // flush the layout before transitions come back on
    bot.style.transition = "";

    bot.addEventListener("click", NoraHome.onPoke);
    bot.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        NoraHome.onPoke();
      }
    });

    NoraHome.watchInteractions();
    NoraHome.scheduleWander();
    NoraHome.connect();

    window.addEventListener("resize", function () {
      NoraHome.moveTo(Math.min(NoraHome.position.x, window.innerWidth - 90));
    });
  };

  /* ── Movement ───────────────────────────────────────────────────────────── */
  // Vertical position is never a free variable — she walks along the bottom
  // strip of the screen, left and right, and never climbs up into the
  // content above it.
  NoraHome.moveTo = function (x, zip) {
    if (!NoraHome.el) return;
    var size = NoraHome.el.offsetWidth || 62;
    x = Math.max(MARGIN, Math.min(x, window.innerWidth - size - MARGIN));
    var y = window.innerHeight - size - GROUND_MARGIN;
    NoraHome.position = { x: x, y: y };

    if (zip && !REDUCED) {
      NoraHome.el.classList.add("is-zipping");
      window.setTimeout(function () {
        NoraHome.el.classList.remove("is-zipping");
      }, 500);
    }
    NoraHome.el.style.transform = "translate3d(" + x + "px," + y + "px,0)";
    NoraHome.positionBubble();
  };

  NoraHome.goTo = function (element) {
    if (!element || !element.getBoundingClientRect) return;
    var box = element.getBoundingClientRect();
    if (box.width === 0 && box.height === 0) return;
    NoraHome.moveTo(box.right + 12, true);
  };

  NoraHome.wander = function () {
    if (!NoraHome.enabled || REDUCED || document.hidden) return;
    NoraHome.moveTo(Math.random() * window.innerWidth);
    NoraHome.scheduleWander();
  };

  NoraHome.scheduleWander = function () {
    window.clearTimeout(NoraHome.idleTimer);
    NoraHome.idleTimer = window.setTimeout(NoraHome.wander, IDLE_WANDER_MS + Math.random() * 6000);
  };

  /* ── Speech ─────────────────────────────────────────────────────────────── */
  NoraHome.say = function (message, options) {
    options = options || {};
    if (!NoraHome.bubble || !message) return;

    NoraHome.setMood(options.mood || "happy");
    NoraHome.bubble.innerHTML = "";
    if (options.badge) {
      var badge = document.createElement("span");
      badge.className = "nh-bubble__badge";
      badge.textContent = options.badge;
      NoraHome.bubble.appendChild(badge);
    }
    NoraHome.bubble.appendChild(document.createTextNode(message));
    NoraHome.bubble.classList.add("is-visible");
    NoraHome.positionBubble();

    window.clearTimeout(NoraHome.bubbleTimer);
    NoraHome.bubbleTimer = window.setTimeout(function () {
      NoraHome.bubble.classList.remove("is-visible");
      NoraHome.setMood("idle");
    }, options.duration || 6000);
  };

  NoraHome.positionBubble = function () {
    if (!NoraHome.bubble || !NoraHome.el) return;
    var size = NoraHome.el.offsetWidth || 62;
    var width = NoraHome.bubble.offsetWidth || 260;
    var left = NoraHome.position.x + size + 10;
    // Flip to the other side rather than overflow the viewport.
    if (left + width > window.innerWidth - MARGIN) {
      left = Math.max(MARGIN, NoraHome.position.x - width - 10);
    }
    NoraHome.bubble.style.left = left + "px";
    NoraHome.bubble.style.top = Math.max(MARGIN, NoraHome.position.y - 12) + "px";
  };

  NoraHome.setMood = function (mood) {
    if (NoraHome.el) NoraHome.el.setAttribute("data-mood", mood || "idle");
  };

  NoraHome.react = function (mood) {
    NoraHome.setMood(mood);
    window.setTimeout(function () { NoraHome.setMood("idle"); }, 2200);
  };

  // Just "Hi" for now — deliberately minimal. What she should actually do
  // when poked is an open question for later, not decided yet.
  NoraHome.onPoke = function () {
    NoraHome.say("Hi", { mood: "happy" });
  };

  /* ── Reacting to the user ───────────────────────────────────────────────── */
  NoraHome.watchInteractions = function () {
    document.addEventListener("click", function (event) {
      var target = event.target.closest("button, a, .card, .tick");
      if (!target || target.closest(".nh-bot")) return;
      NoraHome.goTo(target);
      NoraHome.scheduleWander();
      if (target.classList.contains("tick")) NoraHome.react("proud");
    });

    document.addEventListener("focusin", function (event) {
      if (event.target.matches("input, textarea, select")) {
        NoraHome.goTo(event.target);
        NoraHome.setMood("curious");
      }
    });

    document.addEventListener("visibilitychange", function () {
      if (document.hidden) {
        window.clearTimeout(NoraHome.idleTimer);
      } else {
        NoraHome.setMood("idle");
        NoraHome.scheduleWander();
      }
    });
  };

  /* ── Server link ────────────────────────────────────────────────────────── */
  NoraHome.connect = function () {
    if (!window.WebSocket) return;
    var scheme = window.location.protocol === "https:" ? "wss" : "ws";
    var url = scheme + "://" + window.location.host + "/ws/homebot/";

    try {
      NoraHome.socket = new WebSocket(url);
    } catch (error) {
      return;
    }

    NoraHome.socket.onopen = function () {
      NoraHome.reconnectDelay = 1000;
      window.setInterval(function () {
        NoraHome.send({ type: "heartbeat" });
      }, 30000);
    };

    NoraHome.socket.onmessage = function (event) {
      var data;
      try {
        data = JSON.parse(event.data);
      } catch (error) {
        return;
      }
      NoraHome.handle(data);
    };

    NoraHome.socket.onclose = function () {
      // Back off, but keep trying: the Pi restarts services more often than a
      // server would, and a dead socket should heal itself.
      window.setTimeout(NoraHome.connect, NoraHome.reconnectDelay);
      NoraHome.reconnectDelay = Math.min(NoraHome.reconnectDelay * 2, 30000);
    };
  };

  NoraHome.send = function (payload) {
    if (NoraHome.socket && NoraHome.socket.readyState === 1) {
      NoraHome.socket.send(JSON.stringify(payload));
    }
  };

  NoraHome.handle = function (data) {
    switch (data.type) {
      case "say":
        NoraHome.say(data.message, { mood: data.mood, duration: data.duration_ms });
        break;
      case "react":
        NoraHome.react(data.mood);
        break;
      case "notification":
        NoraHome.onNotification(data);
        break;
      default:
        break;
    }
  };

  NoraHome.onNotification = function (data) {
    var mood = data.severity === "alert" || data.severity === "critical"
      ? "concerned"
      : "curious";
    NoraHome.say(data.title, { mood: mood, badge: "New alert", duration: 8000 });

    var bell = document.querySelector("[data-nh-bell]");
    if (bell) {
      NoraHome.goTo(bell);
      var count = parseInt(bell.getAttribute("data-count") || "0", 10) + 1;
      bell.setAttribute("data-count", String(count));
      bell.textContent = String(count);
      bell.hidden = false;
    }
  };

  document.addEventListener("DOMContentLoaded", function () {
    if (document.documentElement.getAttribute("data-nh-bot") === "off") return;
    NoraHome.mount();
  });
})(window, document);
