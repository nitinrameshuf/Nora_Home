/*
 * The ⌘K palette — Story 47. Replaces the old Apps directory page: instead
 * of a place to browse, a place to jump. Destinations come from
 * nora_home.core.registry.palette_destinations(), rendered server-side into
 * #nh-palette-data (json_script) so this file never invents a URL — the same
 * discipline CLAUDE.md §4 asks of the mockup itself.
 *
 * Filtering matches the mockup's own palette(): a plain case-insensitive
 * substring match over the destination title, nothing fuzzier.
 */
(function (window, document) {
  "use strict";

  var dataEl = document.getElementById("nh-palette-data");
  if (!dataEl) return;

  var dests;
  try {
    dests = JSON.parse(dataEl.textContent);
  } catch (e) {
    dests = [];
  }
  if (!dests.length) return;

  var scrim = null;

  function escapeHtml(s) {
    var div = document.createElement("div");
    div.textContent = s;
    return div.innerHTML;
  }

  function close() {
    if (!scrim) return;
    scrim.remove();
    scrim = null;
  }

  function renderResults(input, results) {
    var q = input.value.trim().toLowerCase();
    var hits = q ? dests.filter(function (d) {
      return d.title.toLowerCase().indexOf(q) !== -1;
    }) : dests;

    if (!hits.length) {
      results.innerHTML = '<div class="empty"><b>No match</b><span>Nothing by that name.</span></div>';
      return;
    }
    results.innerHTML = hits.map(function (d) {
      return '<a class="btn" style="justify-content:flex-start;width:100%;margin-bottom:6px" href="' +
        escapeHtml(d.url) + '">' + escapeHtml(d.title) + "</a>";
    }).join("");
  }

  function open() {
    if (scrim) return;
    scrim = document.createElement("div");
    scrim.className = "scrim";
    scrim.innerHTML =
      '<div class="sheet panel">' +
      "<h3>Go to</h3>" +
      '<input class="srch" placeholder="Type a page&hellip;">' +
      '<div class="body" style="max-height:50vh;overflow:auto;margin-top:9px"></div>' +
      "</div>";
    document.body.appendChild(scrim);

    var input = scrim.querySelector(".srch");
    var results = scrim.querySelector(".body");

    input.addEventListener("input", function () { renderResults(input, results); });
    scrim.addEventListener("click", function (e) {
      if (e.target === scrim) close();
    });
    renderResults(input, results);
    input.focus();
  }

  document.addEventListener("keydown", function (e) {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      scrim ? close() : open();
    } else if (e.key === "Escape" && scrim) {
      close();
    }
  });

  document.addEventListener("click", function (e) {
    if (e.target.closest("[data-nh-palette-open]")) open();
  });
})(window, document);
