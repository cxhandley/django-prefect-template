from django.contrib import admin

from .models import Notification, UserApiKey, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "notify_on_failure", "notify_on_success", "mcp_token_budget")
    search_fields = ("user__email",)


@admin.register(UserApiKey)
class UserApiKeyAdmin(admin.ModelAdmin):
    list_display = ("user", "provider", "label", "masked_suffix", "is_active", "created_at")
    list_filter = ("provider", "is_active")
    search_fields = ("user__email", "label")
    readonly_fields = ("masked_suffix", "created_at", "updated_at", "encrypted_key")
    # Never expose the encrypted_key in a form field — show it read-only only
    fields = (
        "user",
        "provider",
        "label",
        "is_active",
        "base_url",
        "masked_suffix",
        "encrypted_key",
        "created_at",
        "updated_at",
    )


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "notification_type", "is_read", "created_at")
    list_filter = ("notification_type", "is_read")
    search_fields = ("user__email",)
