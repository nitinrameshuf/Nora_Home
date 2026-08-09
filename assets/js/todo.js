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

  /* Recurrence fields on the form only make sense once a type is picked. */
  function wireRecurrenceFields() {
    var select = document.querySelector("[data-recurrence-type]");
    var kindSelect = document.querySelector("[data-recurrence-kind]");
    var groups = document.querySelectorAll("[data-recurrence-for]");
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

  document.addEventListener("DOMContentLoaded", function () {
    wireSimpleActions();
    wireRecurrenceFields();
  });
})(window, document);
