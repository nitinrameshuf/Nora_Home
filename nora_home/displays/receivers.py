"""
Live invalidation — a write on one surface reaches the rest (Story 56).

nora_home.displays held zero receivers before this: the signals in
nora_home.core.signals already fire correctly, and the bus (bus.py) can
already push a message to any screen, but nothing connected the two. A task
completed on a phone left the 24" wall showing stale data until somebody
reloaded it by hand.

Every real surface already goes through the app's own api module (§6), so
these four signals are the complete list of "something changed that a screen
might be showing" — nothing new needed to be taught to fire a signal, this
module only had to start listening.

Debounced through a short cache-backed lock (_schedule_refresh) so
completing five things in a row sends one refresh, not five: a burst of
signals inside DEBOUNCE_SECONDS coalesces into the single delayed broadcast
the first signal in the burst scheduled.

"Scoped" here means by signal, not by display: there is no server-side record
of which page a given screen currently has open (the wall is just whatever
URL its browser tab is on), so a refresh goes to every connected display
rather than a chosen one. What keeps this cheap is that wall-live.js's
"refresh" handler is a plain reload of the page already showing — a wall on
Alerts reloading because a Todo item completed re-fetches Alerts, which is a
harmless no-op, not a jump to a different screen.
"""

from __future__ import annotations

import logging

from django.core.cache import cache
from django.dispatch import receiver

from nora_home.core.signals import (
    escalation_raised,
    item_completed,
    item_missed,
    threshold_crossed,
)

logger = logging.getLogger(__name__)

DEBOUNCE_KEY = "displays:refresh:debounce"
DEBOUNCE_SECONDS = 3


def _schedule_refresh():
    """Coalesce a burst of signals into one delayed broadcast.

    cache.add() only succeeds for the first caller inside the debounce
    window — every call made while that key is still set is a no-op, which
    is the entire debounce mechanism. The task itself carries no state; the
    cache key's TTL is what paces this.
    """
    from nora_home.displays.tasks import broadcast_refresh

    if cache.add(DEBOUNCE_KEY, True, timeout=DEBOUNCE_SECONDS):
        broadcast_refresh.apply_async(countdown=DEBOUNCE_SECONDS)


@receiver(item_completed, dispatch_uid="displays.item_completed")
def _on_item_completed(sender, **kwargs):
    _schedule_refresh()


@receiver(item_missed, dispatch_uid="displays.item_missed")
def _on_item_missed(sender, **kwargs):
    _schedule_refresh()


@receiver(escalation_raised, dispatch_uid="displays.escalation_raised")
def _on_escalation_raised(sender, **kwargs):
    _schedule_refresh()


@receiver(threshold_crossed, dispatch_uid="displays.threshold_crossed")
def _on_threshold_crossed(sender, **kwargs):
    _schedule_refresh()
