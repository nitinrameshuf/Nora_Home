/*
 * Generic modal "Sheet" — Story 53. Fetches a URL's HTML fragment (a
 * `.scrim[data-nh-sheet] > .sheet` pair, e.g. templates/todo/_form_sheet.html)
 * and shows it as an overlay, matching templates/nh/sheet.html's own markup.
 *
 * `[data-sheet-open]`'s value is the URL to fetch. A form inside the sheet
 * with `[data-sheet-form]` submits through fetch too: a JSON {ok, redirect}
 * response navigates there; anything else is HTML (the fragment re-rendered
 * with validation errors) and replaces the sheet in place. This is the same
 * house rule todo.js's simple actions already follow — "reload rather than
 * patch" — just applied to the sheet's own content instead of the whole page.
 *
 * `[data-sheet-close]` closes the current sheet if there is one; if there
 * isn't (the same markup rendered as a full page, e.g. todo/form.html's
 * Cancel link), the click is left alone and navigates normally — no sheet to
 * close, no JS required for that path to work at all.
 */
(function (window, document) {
  "use strict";

  function csrfToken() {
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    if (match) return decodeURIComponent(match[1]);
    var input = document.querySelector("input[name=csrfmiddlewaretoken]");
    return input ? input.value : "";
  }

  function currentSheet() {
    return document.querySelector("[data-nh-sheet]");
  }

  function closeSheet() {
    var sheet = currentSheet();
    if (sheet) sheet.remove();
  }

  function inject(html) {
    closeSheet();
    var wrapper = document.createElement("div");
    wrapper.innerHTML = html;
    var root = wrapper.firstElementChild;
    if (!root) return;
    document.body.appendChild(root);
    document.dispatchEvent(new CustomEvent("nh-sheet:loaded", { detail: { root: root } }));
  }

  function open(url) {
    fetch(url, { credentials: "same-origin", headers: { "X-Requested-With": "fetch" } })
      .then(function (response) { return response.text(); })
      .then(inject);
  }

  function submitForm(form) {
    var submitBtn = form.querySelector("[type=submit]");
    if (submitBtn) submitBtn.disabled = true;

    fetch(form.getAttribute("action") || window.location.href, {
      method: "POST",
      body: new FormData(form),
      credentials: "same-origin",
      headers: { "X-CSRFToken": csrfToken(), "X-Requested-With": "fetch" },
    })
      .then(function (response) {
        var contentType = response.headers.get("Content-Type") || "";
        if (contentType.indexOf("application/json") !== -1) {
          return response.json().then(function (data) {
            window.location.href = data.redirect || window.location.href;
          });
        }
        return response.text().then(inject);
      })
      .catch(function () {
        if (submitBtn) submitBtn.disabled = false;
        if (window.NoraHome && window.NoraHome.say) {
          window.NoraHome.say("That didn't save. Try again?", { mood: "concerned" });
        }
      });
  }

  document.addEventListener("click", function (event) {
    var opener = event.target.closest("[data-sheet-open]");
    if (opener) {
      event.preventDefault();
      open(opener.getAttribute("data-sheet-open"));
      return;
    }

    var closer = event.target.closest("[data-sheet-close]");
    if (closer && currentSheet()) {
      event.preventDefault();
      closeSheet();
      return;
    }

    // A click on the scrim itself (not something inside the sheet panel) —
    // matches the mockup's data-act="close" on the .scrim.
    if (event.target.matches("[data-nh-sheet]")) closeSheet();
  });

  document.addEventListener("submit", function (event) {
    var form = event.target.closest("[data-sheet-form]");
    if (!form || !form.closest("[data-nh-sheet]")) return; // not in a sheet — submit normally
    event.preventDefault();
    submitForm(form);
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && currentSheet()) closeSheet();
  });
})(window, document);
