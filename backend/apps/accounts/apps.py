from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"

    def ready(self):
        import apps.accounts.poll_handlers  # noqa: F401 — registers poll handlers
        import apps.accounts.signals  # noqa: F401
