/*
 * Reporting page charts (docs/Main_App/subsystems/todo.md §10).
 *
 * Every option is already built server-side by `views._reporting_charts()` and
 * shipped in a `json_script` block; this file only finds each holder and hands
 * its option to the house renderer. It deliberately computes nothing — §13's
 * rule is that `nora_home.todo.analytics` is the one place a statistic is
 * derived, and a chart that adjusted a number on the way to the screen would
 * be a second one.
 *
 * Colours come from NoraHomeCharts.theme(), never from here, so Reporting
 * re-themes with the rest of the house when someone flips light/dark.
 */
(function (window, document) {
  "use strict";

  function render() {
    /* No ECharts (offline vendor file missing, or the QA run stubs it out)
       leaves the cards as they are — headings and empty sentences still read
       fine without a canvas, which is the failures-degrade rule. */
    if (!window.NoraHomeCharts || !window.echarts) return;

    var holders = document.querySelectorAll("[data-todo-chart]");
    Array.prototype.forEach.call(holders, function (holder) {
      var source = document.getElementById(holder.getAttribute("data-todo-chart"));
      if (!source) return;

      var option;
      try {
        option = JSON.parse(source.textContent);
      } catch (err) {
        /* One malformed chart must not take the other seven down with it. */
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
