"""
Unit tests for core/table_filters.py — apply_filter() for all
operator / type combinations.
"""

import pytest
from apps.core.table_filters import apply_filter
from django.db.models import Q

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _q_str(q):
    """Return a normalised string representation of a Q object for assertions."""
    return str(q)


# ---------------------------------------------------------------------------
# text filters
# ---------------------------------------------------------------------------


class TestTextFilter:
    def test_contains(self):
        q = apply_filter("status", "text", "contains", "foo")
        assert q == Q(status__icontains="foo")

    def test_not_contains(self):
        q = apply_filter("status", "text", "not_contains", "foo")
        assert q == ~Q(status__icontains="foo")

    def test_eq(self):
        q = apply_filter("status", "text", "eq", "COMPLETED")
        assert q == Q(status__iexact="COMPLETED")

    def test_neq(self):
        q = apply_filter("status", "text", "neq", "COMPLETED")
        assert q == ~Q(status__iexact="COMPLETED")

    def test_starts(self):
        q = apply_filter("flow_name", "text", "starts", "credit")
        assert q == Q(flow_name__istartswith="credit")

    def test_ends(self):
        q = apply_filter("flow_name", "text", "ends", "pipeline")
        assert q == Q(flow_name__iendswith="pipeline")

    def test_empty(self):
        q = apply_filter("error_message", "text", "empty", "")
        assert q == (Q(error_message__isnull=True) | Q(error_message=""))

    def test_not_empty(self):
        q = apply_filter("error_message", "text", "not_empty", "")
        assert q == ~(Q(error_message__isnull=True) | Q(error_message=""))

    def test_unknown_op_returns_none(self):
        assert apply_filter("status", "text", "regex", "foo") is None


# ---------------------------------------------------------------------------
# number filters
# ---------------------------------------------------------------------------


class TestNumberFilter:
    def test_eq(self):
        q = apply_filter("row_count", "number", "eq", "10")
        assert q == Q(row_count__exact=10.0)

    def test_neq(self):
        q = apply_filter("row_count", "number", "neq", "10")
        assert q == ~Q(row_count__exact=10.0)

    def test_gt(self):
        q = apply_filter("row_count", "number", "gt", "5")
        assert q == Q(row_count__gt=5.0)

    def test_gte(self):
        q = apply_filter("row_count", "number", "gte", "5")
        assert q == Q(row_count__gte=5.0)

    def test_lt(self):
        q = apply_filter("row_count", "number", "lt", "100")
        assert q == Q(row_count__lt=100.0)

    def test_lte(self):
        q = apply_filter("row_count", "number", "lte", "100")
        assert q == Q(row_count__lte=100.0)

    def test_empty(self):
        q = apply_filter("row_count", "number", "empty", "")
        assert q == Q(row_count__isnull=True)

    def test_not_empty(self):
        q = apply_filter("row_count", "number", "not_empty", "")
        assert q == Q(row_count__isnull=False)

    def test_non_numeric_val_returns_none(self):
        assert apply_filter("row_count", "number", "eq", "abc") is None

    def test_empty_val_returns_none(self):
        assert apply_filter("row_count", "number", "gt", "") is None

    def test_unknown_op_returns_none(self):
        assert apply_filter("row_count", "number", "contains", "5") is None


# ---------------------------------------------------------------------------
# datetime filters
# ---------------------------------------------------------------------------


class TestDatetimeFilter:
    def test_eq(self):
        q = apply_filter("created_at", "datetime", "eq", "2025-01-01")
        assert q == Q(created_at__date="2025-01-01")

    def test_before(self):
        q = apply_filter("created_at", "datetime", "before", "2025-01-01")
        assert q == Q(created_at__lt="2025-01-01")

    def test_after(self):
        q = apply_filter("created_at", "datetime", "after", "2025-01-01")
        assert q == Q(created_at__gt="2025-01-01")

    def test_empty(self):
        q = apply_filter("completed_at", "datetime", "empty", "")
        assert q == Q(completed_at__isnull=True)

    def test_not_empty(self):
        q = apply_filter("completed_at", "datetime", "not_empty", "")
        assert q == Q(completed_at__isnull=False)

    def test_unknown_op_returns_none(self):
        assert apply_filter("created_at", "datetime", "contains", "2025") is None


# ---------------------------------------------------------------------------
# choice filters
# ---------------------------------------------------------------------------


class TestChoiceFilter:
    def test_eq(self):
        q = apply_filter("status", "choice", "eq", "COMPLETED")
        assert q == Q(status__exact="COMPLETED")

    def test_neq(self):
        q = apply_filter("status", "choice", "neq", "FAILED")
        assert q == ~Q(status__exact="FAILED")

    def test_empty(self):
        q = apply_filter("status", "choice", "empty", "")
        assert q == (Q(status__isnull=True) | Q(status=""))

    def test_not_empty(self):
        q = apply_filter("status", "choice", "not_empty", "")
        assert q == ~(Q(status__isnull=True) | Q(status=""))

    def test_unknown_op_returns_none(self):
        assert apply_filter("status", "choice", "regex", "foo") is None


# ---------------------------------------------------------------------------
# unknown filter type
# ---------------------------------------------------------------------------


def test_unknown_filter_type_returns_none():
    assert apply_filter("field", "boolean", "eq", "true") is None


# ---------------------------------------------------------------------------
# Integration: apply_filter result filters a real queryset
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_filter_applies_to_queryset(flow_execution_factory, user):
    """Smoke-test: a Q object from apply_filter can be .filter()-ed without error."""
    from apps.flows.models import FlowExecution

    flow_execution_factory(triggered_by=user, status="COMPLETED", flow_name="pipeline-a")
    flow_execution_factory(triggered_by=user, status="FAILED", flow_name="pipeline-b")

    q = apply_filter("status", "choice", "eq", "COMPLETED")
    results = FlowExecution.objects.filter(triggered_by=user).filter(q)
    assert results.count() == 1
    assert results.first().flow_name == "pipeline-a"


@pytest.mark.django_db
def test_text_not_contains_filter(flow_execution_factory, user):
    from apps.flows.models import FlowExecution

    flow_execution_factory(triggered_by=user, flow_name="credit-prediction")
    flow_execution_factory(triggered_by=user, flow_name="pipeline-run")

    q = apply_filter("flow_name", "text", "not_contains", "credit")
    results = FlowExecution.objects.filter(triggered_by=user).filter(q)
    assert results.count() == 1
    assert results.first().flow_name == "pipeline-run"
