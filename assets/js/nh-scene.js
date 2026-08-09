/*
 * Keeps the living background's data-daypart/data-season/data-weather fresh
 * without a page reload. Matters because the kiosk and the wall's iframe
 * both sit open for hours at a time — the server-rendered value on first
 * paint would otherwise go stale until something happened to reload the
 * page (a kiosk tap, a manual reload).
 *
 * The actual season/daypart/weather logic lives once, server-side
 * (nora_home.ui.scene), so this only ever applies whatever core:weather_current
 * returns — it never computes anything itself, which is what keeps the wall
 * and kiosk from ever disagreeing about what moment it currently is.
 */
(function (window, document) {
  "use strict";

  if (!document.querySelector(".nh-scene")) return;

  var root = document.documentElement;
  var POLL_MS = 5 * 60 * 1000; // matches the weather integration's own interval

  function apply(data) {
    if (!data) return;
    if (data.season) root.setAttribute("data-season", data.season);
    if (data.daypart) root.setAttribute("data-daypart", data.daypart);
    if (data.weather) root.setAttribute("data-weather", data.weather);
    root.dispatchEvent(new CustomEvent("nh-scene:update", { detail: data }));
  }

  function refresh() {
    fetch("/home/api/weather/", { credentials: "same-origin" })
      .then(function (response) { return response.ok ? response.json() : null; })
      .then(apply)
      .catch(function () { /* stale is fine until the next tick */ });
  }

  window.setInterval(refresh, POLL_MS);
})(window, document);
