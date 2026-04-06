"""
Poll handlers for the accounts app.

Registered via AccountsConfig.ready().

Watcher types
-------------
notification_count
    Tracks the user's unread notification count.  On each tick the handler
    compares the cached count against the client's last-known value.  When
    they differ it tells the frontend to fetch the badge partial so the bell
    indicator updates without a page reload.

    params:
        known_count  – the count the client currently shows (int)
"""

from apps.core.poll_handlers import register
from django.core.cache import cache
from django.urls import reverse


@register("notification_count")
def handle_notification_count(request, watcher_id, params, target):
    """
    Compare the cached unread count against the client's known_count.
    If different, return a directive to fetch the badge partial.
    If the same, return url=None so the frontend skips the fetch but keeps
    the watcher alive for the next tick.
    """
    from .models import Notification

    known_count = params.get("known_count", 0)
    try:
        known_count = int(known_count)
    except (TypeError, ValueError):
        known_count = 0

    cache_key = f"notification_count_{request.user.pk}"
    actual_count = cache.get(cache_key)
    if actual_count is None:
        actual_count = Notification.objects.filter(user=request.user, is_read=False).count()
        cache.set(cache_key, actual_count, 60)

    fetch_url = reverse("accounts:notification_badge") if actual_count != known_count else None

    return {
        "watcher_id": watcher_id,
        "url": fetch_url,
        "target": target,
        "done": False,  # notifications are always watched while the page is open
    }
