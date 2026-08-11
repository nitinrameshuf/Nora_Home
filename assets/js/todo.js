/*
 * The board's actions. Every mutation goes through NoraHome.post() (nh-app.js)
 * for its CSRF handling, and every call checks the resolved promise's `ok` —
 * fetch() does not reject on a 403, which is the trap that left "Add a
 * widget" silently broken for a day (see CLAUDE.md / the build brief).
 *
 * A successful action reloads the page rather than patching the DOM in place.
 * A card leaving one priority column can change that column's live count, the
 * awaiting-approval strip, and the archived list all at once — reproducing
 * that server-side logic in JavaScript is exactly the kind of second engine
 * that quietly drifts from the first one it was copied from.
 */
(function (window, document) {
  "use strict";

  function reportFailure(message) {
    if (window.NoraHome && window.NoraHome.say) {
      window.NoraHome.say(message, { mood: "concerned" });
    }
  }

  function run(button, url, data) {
    button.disabled = true;
    window.NoraHome.post(url, data || {})
      .then(function () { window.location.reload(); })
      .catch(function () {
        button.disabled = false;
        reportFailure("That didn't save. Try again?");
      });
  }

  function wireSimpleActions() {
    document.addEventListener("click", function (event) {
      var button = event.target.closest("[data-todo-action]");
      if (!button || button.disabled) return;

      var action = button.getAttribute("data-todo-action");
      var url = button.getAttribute("data-url");
      if (!url) return;

      if (action === "reject") {
        var reason = window.prompt("Why is this being sent back? (required)");
        if (reason === null) return;
        if (!reason.trim()) {
          reportFailure("A rejection needs a reason.");
          return;
        }
        run(button, url, { reason: reason });
        return;
      }

      if (action === "delete") return; // its own <form>, not this handler

      run(button, url, {});
    });
  }

  /* Recurrence fields on the form only make sense once a type is picked.
   * Re-run whenever a sheet loads (nh-sheet.js): the elements this queries
   * for don't exist yet at DOMContentLoaded when the form arrives later as an
   * injected fragment (Story 53's task Sheet). Safe to call more than once —
   * each call attaches fresh listeners to whatever is in the DOM right now.
   */
  function wireRecurrenceFields(root) {
    root = root || document;
    var select = root.querySelector("[data-recurrence-type]");
    var kindSelect = root.querySelector("[data-recurrence-kind]");
    var groups = root.querySelectorAll("[data-recurrence-for]");
    if (!select || !groups.length) return;

    function sync() {
      var visible = {};
      visible[select.value] = true;
      if (select.value === "fixed" && kindSelect) visible[kindSelect.value] = true;
      groups.forEach(function (group) {
        var wants = group.getAttribute("data-recurrence-for").split(" ");
        group.hidden = !wants.some(function (w) { return visible[w]; });
      });
    }
    select.addEventListener("change", sync);
    if (kindSelect) kindSelect.addEventListener("change", sync);
    sync();
  }

  /* Quick-date chips (Story 53) — fill the real date field rather than
   * replacing it, so "Today"/"Tomorrow"/etc. are a shortcut, not a separate
   * input. Offsets match the mockup's own quick-date map exactly (Today +0,
   * Tomorrow +1, This weekend +6, Next week +7, No date clears it) — plain
   * day offsets, not "next actual Saturday" logic the mockup never had either.
   */
  function isoDateFromToday(offsetDays) {
    var d = new Date();
    d.setDate(d.getDate() + offsetDays);
    var mm = String(d.getMonth() + 1).padStart(2, "0");
    var dd = String(d.getDate()).padStart(2, "0");
    return d.getFullYear() + "-" + mm + "-" + dd;
  }

  function wireQuickDateChips() {
    document.addEventListener("click", function (event) {
      var chip = event.target.closest("[data-quick-date]");
      if (!chip) return;
      var target = document.getElementById(chip.getAttribute("data-target"));
      if (!target) return;
      var days = chip.getAttribute("data-days");
      target.value = days === null ? "" : isoDateFromToday(parseInt(days, 10));
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    wireSimpleActions();
    wireRecurrenceFields();
    wireQuickDateChips();
  });

  document.addEventListener("nh-sheet:loaded", function (event) {
    wireRecurrenceFields(event.detail && event.detail.root);
  });
})(window, document);
