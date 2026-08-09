/* The new front end's seed. No template loads this yet — see nh-next.css.
 *
 * Alpine is imported rather than merely installed so the build actually
 * resolves and bundles a node_modules dependency. An entry that imported
 * nothing would have proven only that Vite can copy a file.
 *
 * Story 45's components are Alpine behaviours attached to Django template
 * tags; this is where Alpine gets started once one of them exists. */

import Alpine from 'alpinejs';

// Deliberately not Alpine.start() yet: starting it would have it scan and take
// ownership of a DOM built by the old front end, which is exactly the pixel
// change this story promises not to make.
window.Alpine = Alpine;
