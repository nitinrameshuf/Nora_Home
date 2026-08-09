/* Picker — one component, two axes. The kiosk's vertical app scroller and the
 * phone's horizontal app rail are the same control rotated: a fixed centre
 * band, a scroll-snap list, and whatever settles in the band becomes live.
 * Ported from docs/Main_App/ui-overhaul-mockup.html's own picker logic
 * (search that file for "the app picker selects by scrolling"), not written
 * fresh — the mockup's version is what was actually reviewed and approved.
 *
 * Two traps the mockup found and this carries over:
 *
 * 1. `scroll` does not bubble, so a listener on an ancestor never fires for a
 *    scrolling descendant. Alpine's `.capture` modifier is the fix — it's the
 *    same `addEventListener(type, fn, true)` the mockup used by hand, just
 *    named. `@scroll.capture.debounce.200ms` on the list itself is both traps
 *    solved in one attribute: capture phase, and "flicking past three items
 *    does not send the wall to each of them in turn".
 *
 * 2. The programmatic centring (on load, and after a click selects an item)
 *    must be flagged, or the scroll it causes gets read back by the debounced
 *    handler as the user choosing something — which then re-centres, which
 *    scrolls, which the handler reads again. `this.auto` is that flag.
 *
 * A third trap that is new here, not in the mockup: percentage padding
 * resolves against the containing block's *width*, even for padding-top on a
 * vertical list — CLAUDE.md §4 documents this costing real time twice
 * already. `centre()` sets padding in pixels via JS for exactly that reason.
 *
 * This is also the house's first real Alpine consumer, and so the one place
 * Alpine.start() is called (Story 44's nh-next.js seed proved the dependency
 * merely resolves, and is gone now that a real one exists). Component
 * registration happens inside the `alpine:init` event rather than at module
 * top level, which is what makes registration order not matter: Alpine
 * dispatches that event itself, synchronously, at the start of
 * Alpine.start() — so `nhPicker` always exists before Alpine goes looking for
 * `x-data="nhPicker()"` in the DOM, regardless of script order.
 */

import Alpine from "alpinejs";

document.addEventListener("alpine:init", () => {
  Alpine.data("nhPicker", () => ({
    auto: false,
    settleTimer: null,

    // Not named `init`: Alpine treats a component method literally called
    // `init` as a reserved lifecycle hook and auto-invokes it itself, with no
    // arguments, in addition to whatever x-init on the element calls
    // explicitly — the two calls collided, and the automatic no-argument one
    // is what threw "Cannot read properties of undefined (reading
    // 'dataset')". `x-init="setup($el)"` in picker.html calls this instead.
    setup(root) {
      this.root = root;
      this.orientation = root.dataset.orientation;
      this.list = root.querySelector(this.orientation === "horizontal" ? ".ph-track" : ".vsel-list");
      this.band = root.querySelector(this.orientation === "horizontal" ? ".ph-band" : ".vsel-band");
      this.itemSelector = this.orientation === "horizontal" ? ".ph-tab" : ".vsel-i";
      // Centre whatever is already marked active, once layout has settled.
      requestAnimationFrame(() => this.centre(this.current(), false));
    },

    current() {
      return this.list.querySelector(`${this.itemSelector}.on`);
    },

    /* Centres `item` in the band. `smooth` is false on first load (nobody
       should see the list glide into place on page load) and true after. */
    centre(item, smooth = true) {
      if (!item) return;
      const vertical = this.orientation !== "horizontal";
      const viewport = vertical ? this.list.clientHeight : this.list.clientWidth;
      if (!viewport) return;

      const extent = vertical ? item.offsetHeight : item.offsetWidth;
      const pad = Math.max(0, (viewport - extent) / 2);
      if (vertical) {
        this.list.style.paddingTop = this.list.style.paddingBottom = `${pad}px`;
      } else {
        this.list.style.paddingLeft = this.list.style.paddingRight = `${pad}px`;
      }

      const start = vertical ? item.offsetTop : item.offsetLeft;
      const target = start - (viewport / 2) + (extent / 2);

      this.auto = true;
      clearTimeout(this.settleTimer);
      this.settleTimer = setTimeout(() => { this.auto = false; }, smooth ? 520 : 60);
      this.list.scrollTo(vertical
        ? { top: target, behavior: smooth ? "smooth" : "auto" }
        : { left: target, behavior: smooth ? "smooth" : "auto" });
    },

    /* @scroll.capture.debounce.200ms on the list. Ignored while a
       programmatic centre() is still settling — see the module docstring. */
    onScroll() {
      if (this.auto) return;

      const bandBox = this.band.getBoundingClientRect();
      const vertical = this.orientation !== "horizontal";
      const centre = vertical ? bandBox.top + bandBox.height / 2 : bandBox.left + bandBox.width / 2;

      let best = null;
      let bestDistance = Infinity;
      this.list.querySelectorAll(this.itemSelector).forEach((el) => {
        const box = el.getBoundingClientRect();
        const mid = vertical ? box.top + box.height / 2 : box.left + box.width / 2;
        const distance = Math.abs(mid - centre);
        if (distance < bestDistance) { bestDistance = distance; best = el; }
      });
      if (!best || best.classList.contains("on")) return;

      this.select(best, { fromScroll: true });
    },

    /* A click (not a scroll) also selects — and then glides the list to
       centre it, same as landing there by hand would. */
    onClick(event) {
      const item = event.target.closest(this.itemSelector);
      if (!item) return;
      this.select(item, { fromScroll: false });
    },

    select(item, { fromScroll }) {
      this.list.querySelectorAll(`${this.itemSelector}.on`).forEach((el) => {
        el.classList.remove("on");
        el.removeAttribute("aria-current");
      });
      item.classList.add("on");
      item.setAttribute("aria-current", "true");

      if (!fromScroll) this.centre(item);

      // The host page decides what a selection means (switch the wall,
      // switch the phone's page, ...) — this component only ever picks.
      // Bubbles, so a plain addEventListener on any ancestor can hear it.
      this.root.dispatchEvent(new CustomEvent("nh-pick", {
        bubbles: true,
        detail: { slug: item.dataset.v },
      }));
    },
  }));
});

Alpine.start();
