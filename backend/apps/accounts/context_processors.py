from django.core.cache import cache


def notification_context(request):
    """
    Adds `unread_notification_count` to every template context.
    Cached per-user for 60 seconds; invalidated on notification create/mark-read.
    """
    if not request.user.is_authenticated:
        return {}

    cache_key = f"notification_count_{request.user.pk}"
    count = cache.get(cache_key)
    if count is None:
        from .models import Notification

        count = Notification.objects.filter(user=request.user, is_read=False).count()
        cache.set(cache_key, count, 60)

    return {"unread_notification_count": count}
