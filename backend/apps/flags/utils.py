"""
Shared flag-resolution helper used by templatetags and decorators.
"""

from django.core.cache import cache

_CACHE_TTL = 300  # 5 minutes


def is_flag_active(flag_name: str, user) -> bool:
    """
    Return True if the named flag is active for *user*.

    The FeatureFlag object is cached for _CACHE_TTL seconds; the per-user
    resolution (allow-list lookup + hash) runs on every call because it is
    cheap and user-specific caching would require per-user cache keys.
    """
    cache_key = f"feature_flag:{flag_name}"
    flag = cache.get(cache_key)

    if flag is None:
        from .models import FeatureFlag

        try:
            flag = FeatureFlag.objects.prefetch_related("enabled_for_users").get(name=flag_name)
        except FeatureFlag.DoesNotExist:
            return False
        cache.set(cache_key, flag, _CACHE_TTL)

    return flag.is_active_for_user(user)
