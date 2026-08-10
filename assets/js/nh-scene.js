/*
 * Keeps the living background's data-daypart/data-weather fresh without a
 * page reload, and generates the star field and weather markup — randomized
 * position/timing, matching docs/Main_App/ui-overhaul-mockup.html's own
 * scene() function rather than a fixed, obviously-repeating pattern, which
 * matters because the kiosk and the wall's iframe both sit open for hours at
 * a time.
 *
 * The actual daypart/weather logic lives once, server-side
 * (nora_home.ui.scene), so this only ever applies whatever core:weather_current
 * returns — it never computes anything itself, which is what keeps the wall
 * and kiosk from ever disagreeing about what moment it currently is.
 */
(function (window, document) {
  "use strict";

  var scene = document.querySelector(".scene");
  if (!scene) return;

  var root = document.documentElement;
  var starsEl = scene.querySelector(".stars");
  var wxEl = scene.querySelector(".wx");
  var POLL_MS = 5 * 60 * 1000; // matches the weather integration's own interval

  function renderStars() {
    if (!starsEl) return;
    var html = "";
    for (var i = 0; i < 22; i++) {
      var left = (Math.random() * 96 + 2).toFixed(1);
      var top = (Math.random() * 48 + 2).toFixed(1);
      var opacity = (Math.random() * 0.5 + 0.45).toFixed(2);
      html += '<i style="left:' + left + '%;top:' + top + '%;opacity:' + opacity + '"></i>';
    }
    starsEl.innerHTML = html;
  }

  function renderWeather(weather) {
    if (!wxEl) return;
    var html = "";
    if (weather === "cloudy" || weather === "rain" || weather === "snow") {
      for (var i = 0; i < 5; i++) {
        var left = i * 22 - 12;
        var top = 5 + i * 8;
        var width = 26 + i * 6;
        var height = 6 + i * 1.4;
        var delay = -(i * 13);
        html += '<span class="cloud" style="left:' + left + '%;top:' + top + '%;' +
          "width:" + width + "%;height:" + height + "%;animation-delay:" + delay + 's"></span>';
      }
    }
    if (weather === "rain") {
      for (var r = 0; r < 60; r++) {
        var rLeft = (Math.random() * 100).toFixed(1);
        var rDelay = -(Math.random()).toFixed(2);
        var rDur = (0.55 + Math.random() * 0.35).toFixed(2);
        html += '<span class="drop" style="left:' + rLeft + '%;animation-delay:' + rDelay +
          "s;animation-duration:" + rDur + 's"></span>';
      }
    }
    if (weather === "snow") {
      for (var s = 0; s < 44; s++) {
        var sLeft = (Math.random() * 100).toFixed(1);
        var sDelay = -(Math.random() * 7).toFixed(2);
        var sDur = (5 + Math.random() * 4).toFixed(2);
        html += '<span class="flake" style="left:' + sLeft + '%;animation-delay:' + sDelay +
          "s;animation-duration:" + sDur + 's"></span>';
      }
    }
    wxEl.innerHTML = html;
  }

  function apply(data) {
    if (!data) return;
    if (data.daypart) root.setAttribute("data-daypart", data.daypart);
    if (data.weather) {
      var changed = root.getAttribute("data-weather") !== data.weather;
      root.setAttribute("data-weather", data.weather);
      if (changed) renderWeather(data.weather);
    }
    root.dispatchEvent(new CustomEvent("nh-scene:update", { detail: data }));
  }

  function refresh() {
    fetch("/home/api/weather/", { credentials: "same-origin" })
      .then(function (response) { return response.ok ? response.json() : null; })
      .then(apply)
      .catch(function () { /* stale is fine until the next tick */ });
  }

  renderStars();
  renderWeather(root.getAttribute("data-weather"));
  window.setInterval(refresh, POLL_MS);
})(window, document);
