from django.contrib import admin

from .models import DashboardWidget, McpSession, UserDashboard


class DashboardWidgetInline(admin.TabularInline):
    model = DashboardWidget
    extra = 0
    readonly_fields = ("created_at",)
    fields = ("widget_type", "title", "position_x", "position_y", "width", "height", "created_at")


@admin.register(UserDashboard)
class UserDashboardAdmin(admin.ModelAdmin):
    list_display = ("owner", "title", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("owner__email", "title")
    inlines = [DashboardWidgetInline]
    readonly_fields = ("created_at", "updated_at")


@admin.register(McpSession)
class McpSessionAdmin(admin.ModelAdmin):
    list_display = ("user", "tokens_used", "tokens_budget", "started_at", "ended_at")
    list_filter = ("ended_at",)
    search_fields = ("user__email",)
    readonly_fields = ("started_at",)
