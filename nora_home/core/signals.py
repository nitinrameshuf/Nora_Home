"""
Platform signals house apps can listen to instead of coupling to each other.

    from django.dispatch import receiver
    from nora_home.core.signals import item_completed

    @receiver(item_completed)
    def celebrate(sender, item, member, **kwargs):
        ...

Sending a signal is the right way for an app to announce something; importing
another app's models is not.
"""

from django.dispatch import Signal

# nora_home.tracker fires these.
item_completed = Signal()      # item, member, completion
item_missed = Signal()         # item, member, due_at
escalation_raised = Signal()   # item, level, notified

# nora_home.telemetry fires this when a reading crosses a configured threshold.
threshold_crossed = Signal()   # series, value, threshold, direction

# nora_home.integrations fires this after a successful poll.
integration_synced = Signal()  # integration, records, duration_ms

# Anything can fire this; the Nora bot listens and reacts on screen.
home_should_react = Signal()   # mood, message, surface
