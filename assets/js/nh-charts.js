/*
 * The house chart theme.
 *
 * Apps return a bare ECharts option — axes, series, data — and this file supplies
 * everything else: colours pulled from the live CSS variables, type, grid, tooltip
 * behaviour, and dark/light handling. That is what keeps a chart written by one
 * family member looking like a chart written by another.
 *
 * App authors should never set colours. If a chart needs a specific colour to carry
 * meaning, use a semantic name: NoraHomeCharts.color("alert").
 */
(function (window, document) {
  "use strict";

  var NoraHomeCharts = { instances: [] };

  function cssVar(name, fallback) {
    var value = getComputedStyle(document.documentElement)
      .getPropertyValue(name)
      .trim();
    return value || fallback;
  }

  NoraHomeCharts.color = function (name) {
    return cssVar("--" + name, "#5cb8ff");
  };

  /* The categorical sequence. Ordered so the first few are distinguishable for
     the most common cases (one series, two series) rather than merely pretty. */
  NoraHomeCharts.palette = function () {
    return [
      cssVar("--accent", "#ff9a5c"),
      cssVar("--info", "#5cb8ff"),
      cssVar("--ok", "#4fd1a5"),
      cssVar("--warn", "#f5c451"),
      cssVar("--violet-500", "#a78bfa"),
      cssVar("--alert", "#ff6b6b")
    ];
  };

  NoraHomeCharts.theme = function () {
    var text = cssVar("--text", "#e6ecf2");
    var dim = cssVar("--text-faint", "#62778c");
    var line = cssVar("--border", "#253140");

    return {
      color: NoraHomeCharts.palette(),
      backgroundColor: "transparent",
      textStyle: {
        fontFamily: cssVar("--font", "ui-sans-serif, system-ui, sans-serif"),
        color: text
      },
      grid: { left: 8, right: 12, top: 24, bottom: 8, containLabel: true },
      categoryAxis: {
        axisLine: { lineStyle: { color: line } },
        axisTick: { show: false },
        axisLabel: { color: dim, fontSize: 11 },
        splitLine: { show: false }
      },
      valueAxis: {
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: dim, fontSize: 11 },
        splitLine: { lineStyle: { color: line, type: "dashed" } },
        nameTextStyle: { color: dim, fontSize: 11 }
      },
      legend: {
        textStyle: { color: dim, fontSize: 11 },
        icon: "roundRect",
        itemWidth: 10,
        itemHeight: 10,
        top: 0
      },
      tooltip: {
        backgroundColor: cssVar("--bg-raised", "#141b24"),
        borderColor: line,
        textStyle: { color: text, fontSize: 12 },
        axisPointer: { lineStyle: { color: line }, crossStyle: { color: line } }
      },
      bar: { itemStyle: { borderRadius: [3, 3, 0, 0] } },
      line: { smooth: true, symbolSize: 6, lineStyle: { width: 2 } }
    };
  };

  /* Build a chart into `element` from an app-supplied option. */
  NoraHomeCharts.render = function (element, option) {
    if (!window.echarts) return null;

    var chart = window.echarts.init(element, null, {
      renderer: "canvas",
      useDirtyRect: true // meaningfully cheaper on a Pi
    });
    chart.setOption(NoraHomeCharts.merge(NoraHomeCharts.theme(), option));
    NoraHomeCharts.instances.push(chart);
    return chart;
  };

  /* Shallow-merge the theme under the app's option: anything the app set wins,
     everything it left out comes from the house. */
  NoraHomeCharts.merge = function (theme, option) {
    var merged = {
      color: theme.color,
      backgroundColor: theme.backgroundColor,
      textStyle: theme.textStyle,
      grid: option.grid || theme.grid,
      tooltip: Object.assign({ trigger: "axis" }, theme.tooltip, option.tooltip || {}),
      legend: option.legend
        ? Object.assign({}, theme.legend, option.legend)
        : undefined
    };

    if (option.xAxis) {
      merged.xAxis = applyAxis(option.xAxis, theme);
    }
    if (option.yAxis) {
      merged.yAxis = applyAxis(option.yAxis, theme);
    }

    Object.keys(option).forEach(function (key) {
      if (["xAxis", "yAxis", "tooltip", "legend", "grid"].indexOf(key) === -1) {
        merged[key] = option[key];
      }
    });

    if (merged.series) {
      merged.series = [].concat(merged.series).map(function (series) {
        var defaults = theme[series.type] || {};
        return Object.assign({}, defaults, series);
      });
    }
    return merged;
  };

  /* ECharts accepts either an object or an array here; preserve whichever the
     app gave us so a dual-axis chart still works. */
  function applyAxis(axis, theme) {
    var themed = [].concat(axis).map(function (one) {
      var base = one.type === "category" ? theme.categoryAxis : theme.valueAxis;
      return Object.assign({}, base, one);
    });
    return Array.isArray(axis) ? themed : themed[0];
  }

  /* Charts do not resize themselves. */
  var resizeTimer;
  window.addEventListener("resize", function () {
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(function () {
      NoraHomeCharts.instances.forEach(function (chart) {
        if (!chart.isDisposed()) chart.resize();
      });
    }, 180);
  });

  /* Re-theme in place when someone flips light/dark, instead of reloading. */
  NoraHomeCharts.retheme = function () {
    NoraHomeCharts.instances.forEach(function (chart) {
      if (chart.isDisposed()) return;
      chart.setOption(NoraHomeCharts.theme());
    });
  };

  window.NoraHomeCharts = NoraHomeCharts;
})(window, document);
