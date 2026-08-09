/*
 * House log charts.
 *
 * Both options are built server-side by nora_home.core.houselog.charts() and
 * shipped in json_script blocks; this file only hands each one to the house
 * renderer. It computes nothing — houselog.py is the single place an entry is
 * counted, and a chart that adjusted a number on its way to the screen would be
 * a second one, disagreeing with the timeline underneath it.
 *
 * Colours come from NoraHomeCharts.theme(), never from here, so the log
 * re-themes along with the rest of the house.
 */
(function (window, document) {
  "use strict";

  function render() {
    /* No ECharts (the vendored bundle missing offline, or a QA run stubbing it
       out) leaves the cards as they are. The timeline below them is the actual
       content of this page and does not depend on a canvas — failures degrade. */
    if (!window.NoraHomeCharts || !window.echarts) return;

    var holders = document.querySelectorAll("[data-log-chart]");
    Array.prototype.forEach.call(holders, function (holder) {
      var source = document.getElementById(holder.getAttribute("data-log-chart"));
      if (!source) return;

      var option;
      try {
        option = JSON.parse(source.textContent);
      } catch (err) {
        /* One malformed chart must not take the other down with it. */
        return;
      }
      window.NoraHomeCharts.render(holder, option);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", render);
  } else {
    render();
  }
})(window, document);
