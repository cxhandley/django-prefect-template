from django.apps import AppConfig


class FlowsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.flows"

    def ready(self):
        import apps.flows.poll_handlers  # noqa: F401 — registers poll handlers
