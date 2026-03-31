"""
ORM filter translation for the DataTable component.

apply_filter(orm_field, filter_type, op, val) → Q object | None
"""

from django.db.models import Q


def _to_number(val):
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def apply_filter(orm_field, filter_type, op, val):
    """
    Return a Q object for the given filter, or None if the combination is
    invalid (unknown operator, unparseable number, etc.).

    Args:
        orm_field   – Django ORM lookup path, e.g. "status" or "parameters__classification"
        filter_type – "text" | "number" | "datetime" | "choice"
        op          – operator key (see design spec §3.1)
        val         – raw string value from the request
    """
    f = orm_field

    if filter_type == "text":
        if op == "contains":
            return Q(**{f"{f}__icontains": val})
        if op == "not_contains":
            return ~Q(**{f"{f}__icontains": val})
        if op == "eq":
            return Q(**{f"{f}__iexact": val})
        if op == "neq":
            return ~Q(**{f"{f}__iexact": val})
        if op == "starts":
            return Q(**{f"{f}__istartswith": val})
        if op == "ends":
            return Q(**{f"{f}__iendswith": val})
        if op == "empty":
            return Q(**{f"{f}__isnull": True}) | Q(**{f: ""})
        if op == "not_empty":
            return ~(Q(**{f"{f}__isnull": True}) | Q(**{f: ""}))

    elif filter_type == "number":
        if op in ("empty",):
            return Q(**{f"{f}__isnull": True})
        if op in ("not_empty",):
            return Q(**{f"{f}__isnull": False})
        num = _to_number(val)
        if num is None:
            return None
        if op == "eq":
            return Q(**{f"{f}__exact": num})
        if op == "neq":
            return ~Q(**{f"{f}__exact": num})
        if op == "gt":
            return Q(**{f"{f}__gt": num})
        if op == "gte":
            return Q(**{f"{f}__gte": num})
        if op == "lt":
            return Q(**{f"{f}__lt": num})
        if op == "lte":
            return Q(**{f"{f}__lte": num})

    elif filter_type == "datetime":
        if op == "eq":
            return Q(**{f"{f}__date": val})
        if op == "before":
            return Q(**{f"{f}__lt": val})
        if op == "after":
            return Q(**{f"{f}__gt": val})
        if op == "empty":
            return Q(**{f"{f}__isnull": True})
        if op == "not_empty":
            return Q(**{f"{f}__isnull": False})

    elif filter_type == "choice":
        if op == "eq":
            return Q(**{f"{f}__exact": val})
        if op == "neq":
            return ~Q(**{f"{f}__exact": val})
        if op == "empty":
            return Q(**{f"{f}__isnull": True}) | Q(**{f: ""})
        if op == "not_empty":
            return ~(Q(**{f"{f}__isnull": True}) | Q(**{f: ""}))

    return None
