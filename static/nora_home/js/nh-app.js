/*
 * Shared front-end behaviour: CSRF-aware fetch, optimistic completion ticks,
 * card auto-refresh, and the theme toggle. Vanilla, no build step.
 *
 * House apps get `NoraHome.post(url, data)` for free — it handles the CSRF token so
 * nobody has to remember to.
 */
(function (window, document) {
  "use strict";

  function csrfToken() {
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    if (match) return decodeURIComponent(match[1]);
    var input = document.querySelector("input[name=csrfmiddlewaretoken]");
    return input ? input.value : "";
  }

  function post(url, data) {
    var body = new FormData();
    var keys = Object.keys(data || {});
    keys.forEach(function (key) {
      body.append(key, data[key]);
    });
    // A FormData with zero parts serializes to just the closing boundary, and
    // this stack's ASGI request parsing rejects that outright with a bare 400
    // before Django even runs — no view, no error body, nothing to debug from
    // the response. Every zero-payload action (a tick with no note, an
    // approve, a skip) hit this. One harmless field keeps the body non-empty.
    if (!keys.length) body.append("_", "1");
    return fetch(url, {
      method: "POST",
      body: body,
      credentials: "same-origin",
      headers: { "X-CSRFToken": csrfToken(), "X-Requested-With": "fetch" }
    }).then(function (response) {
      if (!response.ok) throw new Error("Request failed: " + response.status);
      return response.json();
    });
  }

  /* Completion ticks. The tick flips immediately and rolls back if the server
     disagrees — on a phone in a garage, waiting for a round trip feels broken. */
  function wireTicks() {
    document.addEventListener("click", function (event) {
      var tick = event.target.closest(".tick");
      if (!tick || tick.disabled) return;

      var url = tick.getAttribute("data-complete-url");
      if (!url) return;

      tick.classList.add("is-done");
      tick.disabled = true;

      post(url, {})
        .then(function (result) {
          var row = tick.closest(".item");
          if (row) {
            row.style.transition = "opacity .4s ease, transform .4s ease";
            row.style.opacity = "0";
            row.style.transform = "translateX(18px)";
            window.setTimeout(function () { row.remove(); }, 400);
          }
          if (window.NoraHome && result.streak > 1) {
            window.NoraHome.say(result.streak + " in a row.", { mood: "proud" });
          }
        })
        .catch(function () {
          tick.classList.remove("is-done");
          tick.disabled = false;
          if (window.NoraHome) {
            window.NoraHome.say("That didn't save. Try again?", { mood: "concerned" });
          }
        });
    });
  }

  /* Cards that declare data-refresh-seconds reload themselves in place. */
  function wireCardRefresh() {
    document.querySelectorAll("[data-refresh-seconds]").forEach(function (card) {
      var seconds = parseInt(card.getAttribute("data-refresh-seconds"), 10);
      var url = card.getAttribute("data-refresh-url");
      if (!seconds || !url) return;

      window.setInterval(function () {
        if (document.hidden) return;
        fetch(url, { credentials: "same-origin" })
          .then(function (response) { return response.text(); })
          .then(function (html) { card.innerHTML = html; })
          .catch(function () { /* a failed refresh keeps the stale card */ });
      }, seconds * 1000);
    });
  }

  function wireTheme() {
    var stored = window.localStorage.getItem("nora-home-theme");
    if (stored) document.documentElement.setAttribute("data-theme", stored);

    document.addEventListener("click", function (event) {
      if (!event.target.closest("[data-theme-toggle]")) return;
      var root = document.documentElement;
      var next = root.getAttribute("data-theme") === "light" ? "dark" : "light";
      root.setAttribute("data-theme", next);
      window.localStorage.setItem("nora-home-theme", next);
    });
  }

  /* The profile menu is a native <details>, which only closes again on a
     second click on its own <summary> — not on a click anywhere else, which
     is what every other dropdown/menu convention on the web actually does. */
  function wireProfileMenu() {
    document.addEventListener("click", function (event) {
      document.querySelectorAll(".profile-menu[open]").forEach(function (menu) {
        if (!menu.contains(event.target)) menu.removeAttribute("open");
      });
    });
  }

  /* The 24" wall hides its mouse pointer while the mouse is still, and brings
     it back the moment anyone moves it — the behaviour every video player and
     signage screen has, and for the same reason. The wall is an always-on
     display, so a pointer parked mid-screen sits there for days; but it is
     also the real app now, driven directly from its own sidebar, so hiding it
     permanently means clicking blind.

     Starts idle rather than visible: a wall nobody has touched should never
     show a pointer, and there is no mousemove to hide it again if it did. */
  function wireWallCursor() {
    var root = document.documentElement;
    if (root.getAttribute("data-surface") !== "wall") return;

    var timer = null;
    function wake() {
      root.removeAttribute("data-cursor");
      window.clearTimeout(timer);
      timer = window.setTimeout(function () {
        root.setAttribute("data-cursor", "idle");
      }, 4000);
    }

    ["mousemove", "mousedown", "wheel"].forEach(function (event) {
      document.addEventListener(event, wake, { passive: true });
    });
    root.setAttribute("data-cursor", "idle");
  }

  document.addEventListener("DOMContentLoaded", function () {
    wireTicks();
    wireCardRefresh();
    wireTheme();
    wireProfileMenu();
    wireWallCursor();
  });

  window.NoraHome = window.NoraHome || {};
  window.NoraHome.post = post;
  window.NoraHome.csrfToken = csrfToken;
})(window, document);
