"""Every AI call the house makes, kept so cost and behaviour stay inspectable."""

from __future__ import annotations

from django.conf import settings
from django.db import models

from nora_home.core.models import TimeStampedModel


class AIRun(TimeStampedModel):
    app_slug = models.CharField(max_length=60, db_index=True)
    member = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                               on_delete=models.SET_NULL, related_name="ai_runs")
    tier = models.CharField(max_length=10)
    model = models.CharField(max_length=60)

    prompt = models.TextField()
    response = models.TextField(blank=True)

    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    cached_tokens = models.PositiveIntegerField(default=0)
    cost_usd = models.FloatField(default=0.0)
    duration_ms = models.PositiveIntegerField(default=0)
    stop_reason = models.CharField(max_length=40, blank=True)
    refused = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["app_slug", "-created_at"])]

    def __str__(self):
        return f"{self.app_slug} · {self.model} · ${self.cost_usd:.4f}"

    @property
    def cache_hit_rate(self) -> float:
        total = self.input_tokens + self.cached_tokens
        return (self.cached_tokens / total * 100) if total else 0.0
