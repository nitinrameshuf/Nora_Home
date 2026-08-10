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
 *
 * Story 45, Phase B: the markup this file builds moved onto the arc-reactor
 * component classes (.nh-tile/.card/.card-h/.body/.read/.row/.ck/.empty) —
 * the same ones {% nh_tile %}/{% nh_card %}/{% nh_stat %}/{% nh_list %}
 * render server-side, so a dashboard widget looks identical to any other
 * card in the house. Gridstack's own x/y/w/h units are already a 12-column
 * grid, same as --c/--r, so building a tile is a straight translation, not a
 * redesign.
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
      // Static fallback: honour each widget's width and height on a plain CSS
      // grid — reuses .bento (components.css) rather than a parallel grid
      // class, since .nh-tile's own grid-column/grid-row rule is already
      // scoped to `.bento > .nh-tile` and a widget's --c/--r are set on it
      // either way.
      Dash.gridEl.classList.add("bento");
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
      // rem, not a bare number (which Gridstack treats as px): the wall
      // scales its whole root font-size 1.6x (Story 39) so its text stays
      // readable from three metres, and a tile's *height* has to grow with
      // it or its now-larger content — a stat's big number, in particular —
      // gets clipped by the tile's own overflow:hidden. Found by looking at
      // the wall itself, not by reading this file: a fixed 80px height is
      // exactly the kind of thing that looks correct in isolation and is
      // silently wrong the moment the root font-size it never accounted for
      // changes. 5rem == 80px at the normal 16px root, so nothing changes
      // anywhere else.
      cellHeight: 5,
      cellHeightUnit: "rem",
      margin: 8,
      float: false,
      disableDrag: true,       // opt in via "Rearrange"
      disableResize: true,
      handle: ".dash-grip"
    }, Dash.gridEl);

    Dash.grid.on("change", function () {
      if (Dash.editing) Dash.save();
    });
  };

  Dash.buildTile = function (item) {
    var widget = item.widget;

    var tile = document.createElement("div");
    tile.className = "nh-tile";
    tile.setAttribute("gs-x", item.x);
    tile.setAttribute("gs-y", item.y);
    tile.setAttribute("gs-w", item.w);
    tile.setAttribute("gs-h", item.h);
    // Gridstack's own x/y/w/h are already a 12-column grid, the same units
    // --c/--r expect, so no conversion — just the same numbers under the
    // names components.css's .bento > .nh-tile rule actually reads.
    tile.style.setProperty("--c", item.w);
    tile.style.setProperty("--r", item.h);
    tile.dataset.key = widget.key;

    var card = document.createElement("div");
    card.className = "card panel kind-" + widget.kind;

    var head = document.createElement("div");
    head.className = "card-h";
    var titleWrap = document.createElement("div");
    var title = document.createElement("h4");
    title.textContent = widget.title || "";
    titleWrap.appendChild(title);
    if (widget.subtitle) {
      var sub = document.createElement("span");
      sub.className = "sub";
      sub.textContent = widget.subtitle;
      titleWrap.appendChild(sub);
    }
    head.appendChild(titleWrap);

    var tools = document.createElement("div");
    tools.className = "tools";
    if (widget.app) {
      var app = document.createElement("span");
      app.className = "src";
      app.textContent = widget.app;
      tools.appendChild(app);
    }
    var grip = document.createElement("button");
    grip.className = "dash-grip"; grip.type = "button";
    grip.setAttribute("aria-label", "Drag to move"); grip.textContent = "\u283f";
    tools.appendChild(grip);
    var remove = document.createElement("button");
    remove.className = "dash-remove"; remove.type = "button";
    remove.setAttribute("aria-label", "Remove"); remove.textContent = "\u00d7";
    remove.addEventListener("click", function () { Dash.remove(widget.key); });
    tools.appendChild(remove);
    head.appendChild(tools);
    card.appendChild(head);

    var body = document.createElement("div");
    body.className = "body";
    body.setAttribute("data-body", "");
    card.appendChild(body);

    tile.appendChild(card);
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
    canvas.className = "nh-chart-holder";
    body.appendChild(canvas);
    // Give the tile a frame to reach its final size before ECharts measures it.
    window.requestAnimationFrame(function () {
      window.NoraHomeCharts.render(canvas, widget.option || {});
    });
  }

  function drawStat(body, widget) {
    var stat = widget.stat || {};
    var read = document.createElement("div");
    read.className = "read" + (stat.status ? " " + stat.status : "");

    var value = document.createElement("b");
    value.textContent = stat.value === undefined || stat.value === null ? "—" : stat.value;
    read.appendChild(value);
    if (stat.unit) {
      var unit = document.createElement("span");
      unit.textContent = stat.unit;
      read.appendChild(unit);
    }
    body.appendChild(read);

    if (stat.label || stat.delta) {
      var cap = document.createElement("span");
      cap.className = "cap";
      cap.textContent = stat.label ? (stat.delta ? stat.label + " \u00b7 " + stat.delta : stat.label) : stat.delta;
      body.appendChild(cap);
    }
    if (stat.spark && stat.spark.length > 1) {
      body.appendChild(sparkline(stat.spark));
    }
  }

  /* A sparkline is drawn by hand rather than through ECharts: it is a dozen
     points inside a small tile, and spinning up a chart instance for that is
     wasteful on a Pi. Same 64x20 viewBox and .nh-spark class as {% nh_stat %}'s
     own — see nora_home/ui/templatetags/nh.py's _sparkline_points, which this
     mirrors, so a widget looks the same drawn either way. */
  function sparkline(points) {
    var width = 64;
    var height = 20;
    var low = Math.min.apply(null, points);
    var high = Math.max.apply(null, points);
    var span = high - low || 1;

    var coords = points.map(function (value, index) {
      var x = (index / (points.length - 1)) * width;
      var y = height - ((value - low) / span) * 18 - 1;
      return x.toFixed(1) + "," + y.toFixed(1);
    }).join(" ");

    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 " + width + " " + height);
    svg.setAttribute("class", "nh-spark");
    svg.setAttribute("preserveAspectRatio", "none");

    var line = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
    line.setAttribute("points", coords);
    line.setAttribute("fill", "none");
    line.setAttribute("stroke", "currentColor");
    line.setAttribute("stroke-width", "1.6");

    svg.appendChild(line);
    return svg;
  }

  function drawList(body, widget) {
    var rows = widget.rows || [];
    if (!rows.length) {
      drawNote(body, widget.empty_message || "Nothing here.");
      return;
    }

    rows.forEach(function (row) {
      var item = document.createElement("div");
      item.className = "row" + (row.status === "done" ? " done" : "");

      var ck = document.createElement("span");
      ck.className = "ck" + (row.status === "alert" || row.status === "late" ? " late" : "")
        + (row.status === "done" ? " on" : "");
      if (row.action_url) {
        var tick = document.createElement("button");
        tick.type = "button";
        tick.className = "ck" + (row.status === "alert" || row.status === "late" ? " late" : "");
        tick.setAttribute("aria-label", "Mark " + (row.title || "item") + " done");
        tick.setAttribute("data-complete-url", row.action_url);
        item.appendChild(tick);
      } else {
        item.appendChild(ck);
      }

      if (row.url) {
        var link = document.createElement("a");
        link.className = "t";
        link.href = row.url;
        link.textContent = row.title || "";
        item.appendChild(link);
      } else {
        var title = document.createElement("span");
        title.className = "t";
        title.textContent = row.title || "";
        item.appendChild(title);
      }

      if (row.meta) {
        var meta = document.createElement("span");
        meta.className = "d" + (row.status === "alert" || row.status === "late" ? " late" : "");
        meta.textContent = row.meta;
        item.appendChild(meta);
      }

      body.appendChild(item);
    });
  }

  function drawNote(body, message) {
    var empty = document.createElement("div");
    empty.className = "empty";
    var b = document.createElement("b");
    b.textContent = message;
    empty.appendChild(b);
    body.appendChild(empty);
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
        card.className = "dash-picker__item";
        card.type = "button";
        card.disabled = added;

        var title = document.createElement("div");
        title.className = "dash-picker__title";
        title.textContent = entry.title + (added ? " \u00b7 already added" : "");
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
    var w = entry.w || 4, h = entry.h || 3;
    var pos = Dash.nextSlot(w);

    Dash.placed.push({
      x: pos.x, y: pos.y, w: w, h: h,
      widget: { key: entry.key, kind: entry.kind, title: entry.title,
                subtitle: entry.subtitle, app: entry.app, refresh_seconds: 0 }
    });

    Dash.save().then(function () { window.location.reload(); });
  };

  // Fills the current row left-to-right before starting a new one — a plain
  // "shelf" packer, not general bin-packing, but enough to stop every added
  // widget landing in its own row at x:0 under whatever's already there,
  // which is what actually reads as "clumped and uneven" on screen.
  Dash.nextSlot = function (w) {
    if (!Dash.placed.length) return { x: 0, y: 0 };

    var lastRowY = Dash.placed.reduce(function (max, item) {
      return Math.max(max, item.y);
    }, 0);
    var rowEdge = Dash.placed.reduce(function (edge, item) {
      return item.y === lastRowY ? Math.max(edge, item.x + item.w) : edge;
    }, 0);

    if (rowEdge + w <= 12) return { x: rowEdge, y: lastRowY };

    var bottom = Dash.placed.reduce(function (max, item) {
      return Math.max(max, item.y + item.h);
    }, 0);
    return { x: 0, y: bottom };
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
    }).then(function (response) {
      // fetch() only rejects on a network failure, not on a non-2xx status —
      // an unnoticed 403 (e.g. a missing CSRF token) would otherwise resolve
      // fine here and let Dash.add()'s reload fire as if it had saved.
      if (!response.ok) throw new Error("Save failed: " + response.status);
      return response;
    }).catch(function (error) {
      if (window.NoraHome && window.NoraHome.say) {
        window.NoraHome.say("I couldn't save that layout.", { mood: "concerned" });
      }
      throw error;
    });
  };

  function cssEscape(value) {
    return window.CSS && window.CSS.escape ? window.CSS.escape(value)
                                           : String(value).replace(/"/g, '\\"');
  }

  document.addEventListener("DOMContentLoaded", Dash.init);
  window.Dash = Dash;
})(window, document);
