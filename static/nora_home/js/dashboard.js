/*
 * The home screen.
 *
 * Widgets arrive from the server already rendered as data — a chart option, a stat,
 * a list of rows, or a block of HTML. This file lays them out, draws them, refreshes
 * them on their own timers, and saves the arrangement when someone drags things
 * around.
 *
 * Two optional dependencies, both vendored (see `make vendor`):
 *   Gridstack  drag-and-resize. Without it the grid is static but perfectly usable.
 *   ECharts    charts. Without it chart widgets show a short note instead.
 * The dashboard is deliberately useful with neither, because a Pi with no internet
 * on first boot should still show the family their day.
 */
(function (window, document) {
  "use strict";

  var Dash = {
    root: null,
    gridEl: null,
    grid: null,          // the Gridstack instance, when available
    placed: [],
    catalog: [],
    saveUrl: "",
    widgetUrlTemplate: "",
    timers: []
  };

  Dash.init = function () {
    Dash.root = document.querySelector("[data-dash]");
    if (!Dash.root) return;

    Dash.gridEl = Dash.root.querySelector("[data-dash-grid]");
    Dash.saveUrl = Dash.root.getAttribute("data-save-url");
    Dash.widgetUrlTemplate = Dash.root.getAttribute("data-widget-url");
    Dash.placed = parse(Dash.root.getAttribute("data-placed"), []);
    Dash.catalog = parse(Dash.root.getAttribute("data-catalog"), []);

    Dash.render();
    Dash.wireControls();
  };

  function parse(raw, fallback) {
    try {
      return JSON.parse(raw) || fallback;
    } catch (error) {
      return fallback;
    }
  }

  /* ── layout ──────────────────────────────────────────────────────────────── */
  Dash.render = function () {
    Dash.clearTimers();
    Dash.gridEl.innerHTML = "";

    var empty = Dash.root.querySelector("[data-dash-empty]");
    if (empty) empty.hidden = Dash.placed.length > 0;

    if (!Dash.placed.length) return;

    Dash.placed.forEach(function (item) {
      Dash.gridEl.appendChild(Dash.buildTile(item));
    });

    if (window.GridStack && !window.__nhNoGridstack) {
      Dash.initGridstack();
    } else {
      // Static fallback: honour each widget's width and height on a plain CSS grid.
      Dash.gridEl.classList.add("dash__grid--static");
    }

    Dash.placed.forEach(function (item) {
      Dash.draw(item.widget);
      Dash.scheduleRefresh(item.widget);
    });
  };

  Dash.initGridstack = function () {
    Dash.gridEl.classList.add("grid-stack");
    Array.prototype.forEach.call(Dash.gridEl.children, function (child) {
      child.classList.add("grid-stack-item");
    });

    Dash.grid = window.GridStack.init({
      column: 12,
      cellHeight: 80,
      margin: 8,
      float: false,
      disableDrag: true,       // opt in via "Rearrange"
      disableResize: true,
      handle: ".dash-tile__grip"
    }, Dash.gridEl);

    Dash.grid.on("change", function () {
      if (Dash.editing) Dash.save();
    });
  };

  Dash.buildTile = function (item) {
    var widget = item.widget;

    var tile = document.createElement("div");
    tile.className = "dash-tile-wrap";
    tile.setAttribute("gs-x", item.x);
    tile.setAttribute("gs-y", item.y);
    tile.setAttribute("gs-w", item.w);
    tile.setAttribute("gs-h", item.h);
    tile.style.setProperty("--w", item.w);
    tile.style.setProperty("--h", item.h);
    tile.dataset.key = widget.key;

    var inner = document.createElement("div");
    inner.className = "dash-tile grid-stack-item-content kind-" + widget.kind;
    inner.innerHTML =
      '<div class="dash-tile__head">' +
        '<div>' +
          '<div class="dash-tile__title"></div>' +
          '<div class="dash-tile__sub"></div>' +
        '</div>' +
        '<div class="dash-tile__tools">' +
          '<span class="dash-tile__app"></span>' +
          '<button class="dash-tile__remove" type="button" aria-label="Remove">&times;</button>' +
          '<span class="dash-tile__grip" aria-hidden="true">⠿</span>' +
        '</div>' +
      '</div>' +
      '<div class="dash-tile__body" data-body></div>';

    inner.querySelector(".dash-tile__title").textContent = widget.title || "";
    inner.querySelector(".dash-tile__sub").textContent = widget.subtitle || "";
    inner.querySelector(".dash-tile__app").textContent = widget.app || "";
    inner.querySelector(".dash-tile__remove").addEventListener("click", function () {
      Dash.remove(widget.key);
    });

    tile.appendChild(inner);
    return tile;
  };

  /* ── drawing ─────────────────────────────────────────────────────────────── */
  Dash.draw = function (widget) {
    var tile = Dash.gridEl.querySelector('[data-key="' + cssEscape(widget.key) + '"]');
    if (!tile) return;
    var body = tile.querySelector("[data-body]");
    body.innerHTML = "";

    switch (widget.kind) {
      case "chart":  return drawChart(body, widget);
      case "stat":   return drawStat(body, widget);
      case "list":   return drawList(body, widget);
      case "error":  return drawNote(body, widget.message || "This widget failed.");
      default:       body.innerHTML = widget.html || ""; return;
    }
  };

  function drawChart(body, widget) {
    if (!window.echarts || window.__nhNoECharts) {
      drawNote(body, "Charts need the vendored libraries. Run: make vendor");
      return;
    }
    var canvas = document.createElement("div");
    canvas.className = "dash-tile__chart";
    body.appendChild(canvas);
    // Give the tile a frame to reach its final size before ECharts measures it.
    window.requestAnimationFrame(function () {
      window.NoraHomeCharts.render(canvas, widget.option || {});
    });
  }

  function drawStat(body, widget) {
    var stat = widget.stat || {};
    var wrap = document.createElement("div");
    wrap.className = "dash-stat status-" + (stat.status || "ok");

    var value = document.createElement("div");
    value.className = "dash-stat__value";
    value.textContent = stat.value === undefined || stat.value === null ? "—" : stat.value;
    if (stat.unit) {
      var unit = document.createElement("span");
      unit.className = "dash-stat__unit";
      unit.textContent = " " + stat.unit;
      value.appendChild(unit);
    }
    wrap.appendChild(value);

    if (stat.label) {
      var label = document.createElement("div");
      label.className = "dash-stat__label";
      label.textContent = stat.label;
      wrap.appendChild(label);
    }
    if (stat.delta) {
      var delta = document.createElement("div");
      delta.className = "dash-stat__delta";
      delta.textContent = stat.delta;
      wrap.appendChild(delta);
    }
    if (stat.spark && stat.spark.length > 1) {
      wrap.appendChild(sparkline(stat.spark));
    }
    body.appendChild(wrap);
  }

  /* A sparkline is drawn by hand rather than through ECharts: it is a dozen
     points inside a small tile, and spinning up a chart instance for that is
     wasteful on a Pi. */
  function sparkline(points) {
    var width = 120;
    var height = 28;
    var low = Math.min.apply(null, points);
    var high = Math.max.apply(null, points);
    var span = high - low || 1;

    var coords = points.map(function (value, index) {
      var x = (index / (points.length - 1)) * width;
      var y = height - ((value - low) / span) * (height - 4) - 2;
      return x.toFixed(1) + "," + y.toFixed(1);
    }).join(" ");

    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 " + width + " " + height);
    svg.setAttribute("class", "dash-stat__spark");
    svg.setAttribute("preserveAspectRatio", "none");

    var line = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
    line.setAttribute("points", coords);
    line.setAttribute("fill", "none");
    line.setAttribute("stroke", "currentColor");
    line.setAttribute("stroke-width", "2");
    line.setAttribute("stroke-linecap", "round");
    line.setAttribute("stroke-linejoin", "round");

    svg.appendChild(line);
    return svg;
  }

  function drawList(body, widget) {
    var rows = widget.rows || [];
    if (!rows.length) {
      drawNote(body, widget.empty_message || "Nothing here.");
      return;
    }

    var list = document.createElement("ul");
    list.className = "item-list";

    rows.forEach(function (row) {
      var li = document.createElement("li");
      li.className = "item" + (row.status === "alert" ? " is-overdue" : "");

      if (row.action_url) {
        var tick = document.createElement("button");
        tick.className = "tick";
        tick.type = "button";
        tick.setAttribute("aria-label", "Mark " + (row.title || "item") + " done");
        tick.setAttribute("data-complete-url", row.action_url);
        li.appendChild(tick);
      }

      var content = document.createElement("div");
      content.className = "item-body";

      var title = document.createElement("div");
      title.className = "item-title";
      if (row.url) {
        var link = document.createElement("a");
        link.href = row.url;
        link.textContent = row.title || "";
        title.appendChild(link);
      } else {
        title.textContent = row.title || "";
      }
      content.appendChild(title);

      if (row.meta) {
        var meta = document.createElement("div");
        meta.className = "item-meta";
        meta.textContent = row.meta;
        content.appendChild(meta);
      }

      li.appendChild(content);
      list.appendChild(li);
    });

    body.appendChild(list);
  }

  function drawNote(body, message) {
    var note = document.createElement("p");
    note.className = "dash-tile__note";
    note.textContent = message;
    body.appendChild(note);
  }

  /* ── refresh ─────────────────────────────────────────────────────────────── */
  Dash.scheduleRefresh = function (widget) {
    if (!widget.refresh_seconds) return;

    var timer = window.setInterval(function () {
      if (document.hidden) return;   // never poll a tab nobody is looking at
      fetch(Dash.widgetUrlTemplate.replace("KEY", encodeURIComponent(widget.key)), {
        credentials: "same-origin"
      })
        .then(function (response) { return response.json(); })
        .then(function (fresh) { Dash.draw(fresh); })
        .catch(function () { /* keep the stale tile rather than blanking it */ });
    }, widget.refresh_seconds * 1000);

    Dash.timers.push(timer);
  };

  Dash.clearTimers = function () {
    Dash.timers.forEach(window.clearInterval);
    Dash.timers = [];
  };

  /* ── editing ─────────────────────────────────────────────────────────────── */
  Dash.wireControls = function () {
    document.querySelectorAll("[data-dash-add]").forEach(function (button) {
      button.addEventListener("click", Dash.openPicker);
    });

    var edit = document.querySelector("[data-dash-edit]");
    if (edit) edit.addEventListener("click", Dash.toggleEdit);

    var close = document.querySelector("[data-dash-close]");
    if (close) close.addEventListener("click", Dash.closePicker);
  };

  Dash.toggleEdit = function () {
    Dash.editing = !Dash.editing;
    Dash.root.classList.toggle("is-editing", Dash.editing);

    var button = document.querySelector("[data-dash-edit]");
    if (button) button.textContent = Dash.editing ? "Done" : "Rearrange";

    if (Dash.grid) {
      Dash.grid.enableMove(Dash.editing);
      Dash.grid.enableResize(Dash.editing);
    }
    if (!Dash.editing) Dash.save();
  };

  Dash.openPicker = function () {
    var dialog = document.querySelector("[data-dash-picker]");
    var body = dialog.querySelector("[data-dash-picker-body]");
    var placedKeys = Dash.placed.map(function (item) { return item.widget.key; });

    body.innerHTML = "";
    var groups = {};
    Dash.catalog.forEach(function (entry) {
      (groups[entry.app] = groups[entry.app] || []).push(entry);
    });

    Object.keys(groups).sort().forEach(function (app) {
      var heading = document.createElement("div");
      heading.className = "dash-picker__group";
      heading.textContent = app;
      body.appendChild(heading);

      groups[app].forEach(function (entry) {
        var added = placedKeys.indexOf(entry.key) !== -1;

        var card = document.createElement("button");
        card.className = "dash-picker__item" + (added ? " is-added" : "");
        card.type = "button";
        card.disabled = added;

        var title = document.createElement("div");
        title.className = "dash-picker__title";
        title.textContent = entry.title + (added ? " · already added" : "");
        card.appendChild(title);

        if (entry.description || entry.subtitle) {
          var description = document.createElement("div");
          description.className = "dash-picker__desc";
          description.textContent = entry.description || entry.subtitle;
          card.appendChild(description);
        }

        card.addEventListener("click", function () {
          Dash.add(entry);
          Dash.closePicker();
        });
        body.appendChild(card);
      });
    });

    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  };

  Dash.closePicker = function () {
    var dialog = document.querySelector("[data-dash-picker]");
    if (typeof dialog.close === "function") dialog.close();
    else dialog.removeAttribute("open");
  };

  Dash.add = function (entry) {
    // Drop it below everything already placed rather than guessing at a gap.
    var bottom = Dash.placed.reduce(function (max, item) {
      return Math.max(max, item.y + item.h);
    }, 0);

    Dash.placed.push({
      x: 0, y: bottom, w: entry.w || 4, h: entry.h || 3,
      widget: { key: entry.key, kind: entry.kind, title: entry.title,
                subtitle: entry.subtitle, app: entry.app, refresh_seconds: 0 }
    });

    Dash.save().then(function () { window.location.reload(); });
  };

  Dash.remove = function (key) {
    Dash.placed = Dash.placed.filter(function (item) {
      return item.widget.key !== key;
    });
    var tile = Dash.gridEl.querySelector('[data-key="' + cssEscape(key) + '"]');
    if (tile) {
      if (Dash.grid) Dash.grid.removeWidget(tile);
      else tile.remove();
    }
    Dash.save();
    if (!Dash.placed.length) Dash.render();
  };

  Dash.save = function () {
    var items = Dash.placed.map(function (item) {
      var node = Dash.gridEl.querySelector(
        '[data-key="' + cssEscape(item.widget.key) + '"]');
      var position = (Dash.grid && node) ? node.gridstackNode : null;

      return {
        key: item.widget.key,
        x: position ? position.x : item.x,
        y: position ? position.y : item.y,
        w: position ? position.w : item.w,
        h: position ? position.h : item.h
      };
    });

    return fetch(Dash.saveUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": (window.NoraHome && window.NoraHome.csrfToken) ? window.NoraHome.csrfToken() : ""
      },
      body: JSON.stringify({ items: items })
    }).catch(function () {
      if (window.NoraHome && window.NoraHome.say) {
        window.NoraHome.say("I couldn't save that layout.", { mood: "concerned" });
      }
    });
  };

  function cssEscape(value) {
    return window.CSS && window.CSS.escape ? window.CSS.escape(value)
                                           : String(value).replace(/"/g, '\\"');
  }

  document.addEventListener("DOMContentLoaded", Dash.init);
  window.Dash = Dash;
})(window, document);
