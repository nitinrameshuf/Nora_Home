/*
 * Turns the phone's bottom tab bar into real navigation — Story 49.
 *
 * nh-picker.js (the shared Picker component driving .ph-rail) only ever
 * picks: it updates which tab looks selected and dispatches a bubbling
 * `nh-pick` event carrying the picked slug, then leaves what that means to
 * the host page — correct, because on the kiosk the same component's
 * vertical form (Story 50) will mean "switch what the wall shows", not
 * "navigate", and the component has no business assuming either.
 *
 * On the phone a pick means a real page load, so this is that host-page
 * decision: look the slug up against the same {slug, url} list the tabs were
 * rendered from (nora_home.core.registry.phone_tabs(), via #nh-phone-tabs-data)
 * and navigate there. Scoped to `.ph-rail` specifically so a future picker
 * used for something else on the same page can't be misread as a tab pick.
 */
(function (window, document) {
  "use strict";

  var dataEl = document.getElementById("nh-phone-tabs-data");
  if (!dataEl) return;

  var tabs;
  try {
    tabs = JSON.parse(dataEl.textContent);
  } catch (e) {
    tabs = [];
  }
  if (!tabs.length) return;

  var urlBySlug = {};
  tabs.forEach(function (tab) { urlBySlug[tab.slug] = tab.url; });

  document.addEventListener("nh-pick", function (event) {
    if (!event.target.classList || !event.target.classList.contains("ph-rail")) return;
    var url = urlBySlug[event.detail.slug];
    // Already there — the picker's own centring is enough; a navigation
    // would just reload the page under someone's thumb.
    if (url && url !== window.location.pathname) window.location.href = url;
  });
})(window, document);
