"""
Pipeline backend registry.

Usage:
    from apps.flows.backends import get_backend
    backend = get_backend()          # returns configured PipelineBackend instance
"""

from django.conf import settings


def get_backend():
    """Return a PipelineBackend instance for the currently configured backend."""
    name = getattr(settings, "PIPELINE_BACKEND", "doit")
    if name == "prefect":
        from apps.flows.backends.prefect import PrefectBackend

        return PrefectBackend()
    # Default — doit
    from apps.flows.backends.doit import DoitBackend

    return DoitBackend()
