from django.contrib import admin

from .models import FeatureFlag


@admin.register(FeatureFlag)
class FeatureFlagAdmin(admin.ModelAdmin):
    list_display = ("name", "is_enabled", "rollout_percentage", "user_count")
    list_editable = ("is_enabled", "rollout_percentage")
    filter_horizontal = ("enabled_for_users",)
    search_fields = ("name", "description")

    @admin.display(description="Explicit users")
    def user_count(self, obj):
        return obj.enabled_for_users.count()

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        _invalidate_flag_cache(obj.name)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        _invalidate_flag_cache(form.instance.name)


def _invalidate_flag_cache(flag_name: str):
    from django.core.cache import cache

    cache.delete(f"feature_flag:{flag_name}")
