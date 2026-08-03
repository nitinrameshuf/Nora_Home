"""
Concrete integrations. Importing this package registers each one (see the
`@register` decorator in nora_home.integrations.base) — done once, from
IntegrationsConfig.ready(), so it happens exactly at Django startup.
"""

from nora_home.integrations.providers import weather  # noqa: F401
