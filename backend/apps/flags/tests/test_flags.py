"""
Tests for the feature flags app (BL-020).
"""

import pytest
from apps.flags.decorators import require_flag
from apps.flags.models import FeatureFlag
from apps.flags.utils import is_flag_active
from django.contrib.auth import get_user_model
from django.http import Http404
from django.test import RequestFactory

User = get_user_model()


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def clear_flag_cache():
    """Clear the flag cache before and after each test to prevent inter-test pollution."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def user(db):
    return User.objects.create_user(username="flaguser", email="flag@example.com", password="pass")


@pytest.fixture
def flag(db):
    return FeatureFlag.objects.create(name="test-feature", description="Test flag")


# ── FeatureFlag.is_active_for_user ────────────────────────────────────────────


@pytest.mark.django_db
def test_flag_off_by_default(flag, user):
    assert flag.is_active_for_user(user) is False


@pytest.mark.django_db
def test_flag_global_on(flag, user):
    flag.is_enabled = True
    flag.save()
    assert flag.is_active_for_user(user) is True


@pytest.mark.django_db
def test_flag_explicit_user_overrides_global_off(flag, user):
    flag.is_enabled = False
    flag.save()
    flag.enabled_for_users.add(user)
    assert flag.is_active_for_user(user) is True


@pytest.mark.django_db
def test_flag_explicit_user_not_in_list(flag, user):
    other = User.objects.create_user(username="other", email="other@example.com", password="pass")
    flag.enabled_for_users.add(other)
    assert flag.is_active_for_user(user) is False


@pytest.mark.django_db
def test_flag_rollout_100_percent(flag, user):
    flag.rollout_percentage = 100
    flag.save()
    assert flag.is_active_for_user(user) is True


@pytest.mark.django_db
def test_flag_rollout_0_percent(flag, user):
    flag.rollout_percentage = 0
    flag.is_enabled = False
    flag.save()
    assert flag.is_active_for_user(user) is False


@pytest.mark.django_db
def test_flag_rollout_is_deterministic(flag, user):
    flag.rollout_percentage = 50
    flag.save()
    result_1 = flag.is_active_for_user(user)
    result_2 = flag.is_active_for_user(user)
    assert result_1 == result_2


@pytest.mark.django_db
def test_flag_unauthenticated_user_uses_global(flag):
    from unittest.mock import Mock

    anon = Mock()
    anon.is_authenticated = False

    flag.is_enabled = True
    flag.save()
    assert flag.is_active_for_user(anon) is True

    flag.is_enabled = False
    flag.save()
    assert flag.is_active_for_user(anon) is False


# ── is_flag_active (cache helper) ────────────────────────────────────────────


@pytest.mark.django_db
def test_is_flag_active_returns_false_for_missing_flag(user):
    assert is_flag_active("nonexistent-flag", user) is False


@pytest.mark.django_db
def test_is_flag_active_returns_true_when_enabled(flag, user):
    flag.is_enabled = True
    flag.save()
    assert is_flag_active(flag.name, user) is True


@pytest.mark.django_db
def test_is_flag_active_uses_cache(flag, user, settings):
    from django.core.cache import cache

    flag.is_enabled = True
    flag.save()

    # Prime the cache
    is_flag_active(flag.name, user)

    # Change the DB value without clearing cache
    FeatureFlag.objects.filter(pk=flag.pk).update(is_enabled=False)

    # Should still return True from cache
    assert is_flag_active(flag.name, user) is True

    # After cache clear, should return updated value
    cache.delete(f"feature_flag:{flag.name}")
    assert is_flag_active(flag.name, user) is False


# ── @require_flag decorator ───────────────────────────────────────────────────


@pytest.mark.django_db
def test_require_flag_raises_404_when_off(flag, user):
    factory = RequestFactory()
    request = factory.get("/")
    request.user = user

    @require_flag(flag.name)
    def my_view(request):
        return "ok"

    with pytest.raises(Http404):
        my_view(request)


@pytest.mark.django_db
def test_require_flag_passes_when_on(flag, user):
    flag.is_enabled = True
    flag.save()

    factory = RequestFactory()
    request = factory.get("/")
    request.user = user

    @require_flag(flag.name)
    def my_view(request):
        return "ok"

    assert my_view(request) == "ok"


# ── template tag ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_flag_template_tag_renders_when_active(flag, user):
    from django.template import Context, Template

    flag.is_enabled = True
    flag.save()

    template = Template("{% load flags %}{% flag 'test-feature' %}shown{% endflag %}")
    # Provide a minimal request-like object
    from unittest.mock import Mock

    request = Mock()
    request.user = user
    output = template.render(Context({"request": request}))
    assert "shown" in output


@pytest.mark.django_db
def test_flag_template_tag_hides_when_inactive(flag, user):
    from django.template import Context, Template

    template = Template("{% load flags %}{% flag 'test-feature' %}shown{% endflag %}")

    from unittest.mock import Mock

    request = Mock()
    request.user = user
    output = template.render(Context({"request": request}))
    assert "shown" not in output
