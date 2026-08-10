/*
 * The home screen.
 *
 * Widgets arrive from the server already rendered as data — a chart option, a stat,
 * a list of rows, or a block of HTML. This file lays them out, draws them, refreshes
 * them on their own timers, and saves the arrangement when someone rearranges it.
 *
 * Story 48: **the layout is an ordered list, not a set of coordinates.** Each item
 * is {key, size} where size is one of S/M/L/XL, and CSS grid places the tiles with
 * `grid-auto-flow: row dense` (see .bento in components.css). Gridstack is gone —
 * absolute x/y/w/h is what made a screen able to look ragged in the first place,
 * and with whole-cell sizes on a 12-column grid no arrangement can. Reordering is
 * moving an item one step through the list, which is a button rather than a drag
 * because the phone is a first-class surface and HTML5 drag-and-drop does not work
 * on touch without a polyfill.
 *
 * One optional dependency, vendored (see `make vendor`):
 *   ECharts    charts. Without it chart widgets show a short note instead.
 * The dashboard is deliberately useful without it, because a Pi with no internet
 * on first boot should still show the family their day.
 *
 * The markup built here is the arc-reactor component set (.nh-tile/.card/.card-h/
 * .body/.read/.row/.ck/.empty) — the same classes {% nh_tile %}/{% nh_card %}/
 * {% nh_stat %}/{% nh_list %} render server-side, so a dashboard widget looks
 * identical to any other card in the house.
 */
(function (window, document) {
  "use strict";

  var Dash = {
    root: null,
    gridEl: null,
    placed: [],       // ordered [{widget}] — the order IS the layout
    catalog: [],
    saveUrl: "",
    widgetUrlTemplate: "",
    editing: false,
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
    Dash.gridEl.classList.add("bento");

    var empty = Dash.root.querySelector("[data-dash-empty]");
    if (empty) empty.hidden = Dash.placed.length > 0;

    if (!Dash.placed.length) return;

    Dash.placed.forEach(function (item, index) {
      Dash.gridEl.appendChild(Dash.buildTile(item, index));
    });

    Dash.placed.forEach(function (item) {
      Dash.draw(item.widget);
      Dash.scheduleRefresh(item.widget);
    });
  };

  Dash.buildTile = function (item, index) {
    var widget = item.widget;

    var tile = document.createElement("div");
    tile.className = "nh-tile";
    // The server already resolved the size to cells — the browser never owns
    // that table, so a size the widget stopped offering renders as whatever
    // the server fell back to rather than as two different answers.
    tile.style.setProperty("--c", widget.c);
    tile.style.setProperty("--r", widget.r);
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

    // One button per size this widget declares. Outside edit mode they are
    // hidden by CSS and the source app's name shows instead.
    if (widget.app) {
      var app = document.createElement("span");
      app.className = "src";
      app.textContent = widget.app;
      tools.appendChild(app);
    }
    (widget.sizes || []).forEach(function (name) {
      var button = document.createElement("button");
      button.className = "szbtn";
      button.type = "button";
      button.textContent = name;
      button.setAttribute("aria-pressed", String(name === widget.size));
      button.setAttribute("aria-label", "Size " + name + ": " + (widget.title || ""));
      button.addEventListener("click", function () { Dash.resize(widget.key, name); });
      tools.appendChild(button);
    });

    tools.appendChild(moveButton("\u2039", "Move earlier", index === 0, function () {
      Dash.move(index, -1);
    }));
    tools.appendChild(moveButton("\u203a", "Move later",
      index === Dash.placed.length - 1, function () { Dash.move(index, 1); }));

    var remove = document.createElement("button");
    remove.className = "dash-remove"; remove.type = "button";
    remove.setAttribute("aria-label", "Remove " + (widget.title || "widget"));
    remove.textContent = "\u00d7";
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

  function moveButton(glyph, label, disabled, handler) {
    var button = document.createElement("button");
    button.className = "dash-move";
    button.type = "button";
    button.textContent = glyph;
    button.setAttribute("aria-label", label);
    button.disabled = disabled;
    button.addEventListener("click", handler);
    return button;
  }

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
  /* Always carries the size. A list at M is a readout and at L is four rows, so
     refreshing without it would quietly redraw the tile as a different variant
     — the tile would keep its cells and change what is inside them. */
  Dash.fetchWidget = function (key, size) {
    var url = Dash.widgetUrlTemplate.replace("KEY", encodeURIComponent(key))
      + "?size=" + encodeURIComponent(size || "");
    return fetch(url, { credentials: "same-origin" })
      .then(function (response) { return response.ok ? response.json() : null; });
  };

  Dash.scheduleRefresh = function (widget) {
    if (!widget.refresh_seconds) return;

    var timer = window.setInterval(function () {
      if (document.hidden) return;   // never poll a tab nobody is looking at
      Dash.fetchWidget(widget.key, widget.size)
        .then(function (fresh) { if (fresh) Dash.draw(fresh); })
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
  };

  /* Change one widget's size. The server owns what a size means — a list at M
     is a readout and at L is four rows — so this refetches that widget rather
     than resizing the tile around stale content, which is the whole difference
     between "a designed state" and "the same content stretched". */
  Dash.resize = function (key, size) {
    var item = Dash.placed.filter(function (each) {
      return each.widget.key === key;
    })[0];
    if (!item || item.widget.size === size) return;

    item.widget.size = size;
    Dash.save()
      .then(function () { return Dash.fetchWidget(key, size); })
      .then(function (fresh) {
        if (fresh) item.widget = fresh;
        Dash.render();
      })
      .catch(function () { /* save() already told the family */ });
  };

  Dash.move = function (index, delta) {
    var target = index + delta;
    if (target < 0 || target >= Dash.placed.length) return;
    var moved = Dash.placed.splice(index, 1)[0];
    Dash.placed.splice(target, 0, moved);
    Dash.render();
    Dash.save();
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
    // Appended, not slotted: order is the layout and `dense` does the packing,
    // so there is no "next free position" to work out — the shelf packer this
    // replaced existed only because coordinates had to be invented by hand.
    Dash.placed.push({
      widget: { key: entry.key, kind: entry.kind, title: entry.title,
                subtitle: entry.subtitle, app: entry.app, refresh_seconds: 0,
                size: entry.size, sizes: entry.sizes || [] }
    });

    Dash.save().then(function () { window.location.reload(); });
  };

  Dash.remove = function (key) {
    Dash.placed = Dash.placed.filter(function (item) {
      return item.widget.key !== key;
    });
    Dash.render();
    Dash.save();
  };

  Dash.save = function () {
    var items = Dash.placed.map(function (item) {
      return { key: item.widget.key, size: item.widget.size };
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
