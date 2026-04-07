"""
Utility helpers for the DataTable component.

Used by function-based views; not a class mixin so it stays compatible with
the existing FBV pattern in apps/flows/views.py.
"""

import json

from .table_filters import apply_filter


def get_filtered_queryset(request, qs, filter_fields, table_columns, default_sort="-created_at"):
    """
    Apply f_field[], f_op[], f_val[] query params as ORM filters.
    Apply the `sort` query param as an ORDER BY.

    Returns (filtered_qs, sort_field_string).

    Args:
        request        – Django HttpRequest
        qs             – base QuerySet (already scoped to the current user)
        filter_fields  – dict of {field_key: {"type": "...", "orm_field": "..."}}
        table_columns  – list of column dicts (used to validate allowed sort fields)
        default_sort   – fallback ORDER BY string
    """
    fields = request.GET.getlist("f_field[]")
    ops = request.GET.getlist("f_op[]")
    vals = request.GET.getlist("f_val[]")

    for field, op, val in zip(fields, ops, vals, strict=False):
        cfg = filter_fields.get(field)
        if not cfg:
            continue
        # empty/not_empty don't need a value; other ops need a non-blank val
        if op not in ("empty", "not_empty") and not val.strip():
            continue
        q = apply_filter(cfg["orm_field"], cfg["type"], op, val.strip())
        if q is not None:
            qs = qs.filter(q)

    # Validate requested sort against allowed sort fields to prevent ORM injection
    sort = request.GET.get("sort", default_sort)
    allowed = set()
    for col in table_columns:
        if col.get("sortable") and col.get("sort_field"):
            sf = col["sort_field"]
            allowed.add(sf)
            allowed.add(f"-{sf}")
    if allowed and sort not in allowed:
        sort = default_sort

    return qs.order_by(sort), sort


def build_active_filters(request):
    """
    Return a list of {field, op, value} dicts from the current request's
    f_field[], f_op[], f_val[] params.  Used to re-populate filter chips and
    the Alpine activeFilters array on page load.
    """
    fields = request.GET.getlist("f_field[]")
    ops = request.GET.getlist("f_op[]")
    vals = request.GET.getlist("f_val[]")
    result = []
    for field, op, val in zip(fields, ops, vals, strict=False):
        if field and op:
            result.append({"field": field, "op": op, "value": val})
    return result


def build_table_config_json(table_config):
    """
    Serialise the parts of table_config that the Alpine component needs at
    runtime into a JSON string safe to embed with |safe.

    Converts snake_case Python keys → camelCase JS keys.
    """
    field_configs = {}
    for col in table_config["columns"]:
        if col.get("filterable"):
            field_configs[col["key"]] = {
                "type": col.get("filter_type", "text"),
                "label": col["label"],
                "choices": col.get("filter_choices", []),
            }

    bulk_actions = []
    for action in table_config.get("bulk_actions", []):
        bulk_actions.append(
            {
                "key": action["key"],
                "label": action["label"],
                "method": action.get("method", "GET"),
                "url": action["url"],
                "idParam": action.get("id_param", "ids"),
                "idSep": action.get("id_sep", ","),
                "minSelect": action.get("min_select", 1),
                "maxSelect": action.get("max_select"),  # None → null in JSON
                "confirm": action.get("confirm", False),
                "confirmMessage": action.get("confirm_message", "Are you sure?"),
                "variant": action.get("variant", "btn-outline btn-sm"),
            }
        )

    payload = {
        "tableId": table_config["table_id"],
        "hxUrl": table_config["hx_url"],
        "hxTarget": table_config["hx_target"],
        "sortField": table_config.get("sort_field", ""),
        "activeFilters": table_config.get("active_filters", []),
        "fieldConfigs": field_configs,
        "bulkActions": bulk_actions,
        "allIdsUrl": table_config.get("all_ids_url"),
        "totalCount": table_config.get("total_count", 0),
        "pageRowIds": table_config.get("page_row_ids", []),
    }
    return json.dumps(payload)


def build_filter_query_string(request):
    """
    Return the current query string with the `page` param removed, suitable
    for appending `&page=N` to build paginated HTMX URLs that preserve filters.
    """
    params = request.GET.copy()
    params.pop("page", None)
    return params.urlencode()
