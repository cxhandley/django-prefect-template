"""
Tool definitions for the MCP dashboard builder.

Each tool function calls back to the Django internal API to read or mutate
dashboard state.  The Django URL is resolved from the DJANGO_INTERNAL_URL
environment variable.

Tool schemas are registered in main.py alongside each tool handler.
"""

import os

import httpx

DJANGO_URL = os.environ.get("DJANGO_INTERNAL_URL", "http://web:8000")
MCP_INTERNAL_SECRET = os.environ.get("MCP_INTERNAL_SECRET", "")

_INTERNAL_HEADERS = {
    "Authorization": f"Bearer {MCP_INTERNAL_SECRET}",
    "Content-Type": "application/json",
}


def _internal_get(path: str) -> dict:
    url = f"{DJANGO_URL}/internal/mcp/{path}"
    resp = httpx.get(url, headers=_INTERNAL_HEADERS, timeout=10.0)
    resp.raise_for_status()
    return resp.json()


def _internal_post(path: str, body: dict) -> dict:
    url = f"{DJANGO_URL}/internal/mcp/{path}"
    resp = httpx.post(url, json=body, headers=_INTERNAL_HEADERS, timeout=10.0)
    resp.raise_for_status()
    return resp.json()


# ── Tool implementations ───────────────────────────────────────────────────────


def add_metric_card(
    dashboard_id: int,
    title: str,
    field: str,
    aggregation: str = "count",
    label: str = "",
    unit: str = "",
    position_x: int = 0,
    position_y: int = 0,
) -> dict:
    """Add a metric card widget to the dashboard."""
    return _internal_post(
        f"dashboard/{dashboard_id}/widgets/",
        {
            "widget_type": "METRIC_CARD",
            "title": title,
            "config": {"field": field, "aggregation": aggregation, "label": label, "unit": unit},
            "position_x": position_x,
            "position_y": position_y,
            "width": 1,
            "height": 1,
        },
    )


def add_line_chart(
    dashboard_id: int,
    title: str,
    x_field: str,
    y_field: str,
    label: str = "",
    color: str = "#4f46e5",
    position_x: int = 0,
    position_y: int = 0,
    width: int = 2,
    height: int = 2,
) -> dict:
    """Add a line chart widget to the dashboard."""
    return _internal_post(
        f"dashboard/{dashboard_id}/widgets/",
        {
            "widget_type": "LINE_CHART",
            "title": title,
            "config": {"x_field": x_field, "y_field": y_field, "label": label, "color": color},
            "position_x": position_x,
            "position_y": position_y,
            "width": width,
            "height": height,
        },
    )


def add_bar_chart(
    dashboard_id: int,
    title: str,
    x_field: str,
    y_field: str,
    label: str = "",
    color: str = "#4f46e5",
    position_x: int = 0,
    position_y: int = 0,
    width: int = 2,
    height: int = 2,
) -> dict:
    """Add a bar chart widget to the dashboard."""
    return _internal_post(
        f"dashboard/{dashboard_id}/widgets/",
        {
            "widget_type": "BAR_CHART",
            "title": title,
            "config": {"x_field": x_field, "y_field": y_field, "label": label, "color": color},
            "position_x": position_x,
            "position_y": position_y,
            "width": width,
            "height": height,
        },
    )


def add_table(
    dashboard_id: int,
    title: str,
    fields: list,
    limit: int = 10,
    order_by: str = "",
    order_dir: str = "desc",
    position_x: int = 0,
    position_y: int = 0,
    width: int = 4,
    height: int = 2,
) -> dict:
    """Add a data table widget to the dashboard."""
    return _internal_post(
        f"dashboard/{dashboard_id}/widgets/",
        {
            "widget_type": "TABLE",
            "title": title,
            "config": {
                "fields": fields,
                "limit": limit,
                "order_by": order_by,
                "order_dir": order_dir,
            },
            "position_x": position_x,
            "position_y": position_y,
            "width": width,
            "height": height,
        },
    )


def add_score_distribution(
    dashboard_id: int,
    title: str,
    bins: int = 10,
    label: str = "",
    position_x: int = 0,
    position_y: int = 0,
    width: int = 2,
    height: int = 2,
) -> dict:
    """Add a score distribution histogram widget."""
    return _internal_post(
        f"dashboard/{dashboard_id}/widgets/",
        {
            "widget_type": "SCORE_DISTRIBUTION",
            "title": title,
            "config": {"bins": bins, "label": label},
            "position_x": position_x,
            "position_y": position_y,
            "width": width,
            "height": height,
        },
    )


def update_widget(
    dashboard_id: int,
    widget_id: int,
    title: str | None = None,
    config: dict | None = None,
    position_x: int | None = None,
    position_y: int | None = None,
    width: int | None = None,
    height: int | None = None,
) -> dict:
    """Update an existing widget's title, config, or position."""
    body: dict = {"id": widget_id}
    if title is not None:
        body["title"] = title
    if config is not None:
        body["config"] = config
    if position_x is not None:
        body["position_x"] = position_x
    if position_y is not None:
        body["position_y"] = position_y
    if width is not None:
        body["width"] = width
    if height is not None:
        body["height"] = height
    return _internal_post(f"dashboard/{dashboard_id}/widgets/", body)


def get_widget(dashboard_id: int, widget_id: int) -> dict:
    """Retrieve the current config of a widget."""
    return _internal_get(f"dashboard/{dashboard_id}/widgets/{widget_id}/")


# ── Tool registry for main.py ─────────────────────────────────────────────────

TOOL_SCHEMAS = [
    {
        "name": "add_metric_card",
        "description": "Add a metric card widget showing a single aggregated value (count, sum, avg, min, max).",
        "parameters": {
            "type": "object",
            "properties": {
                "dashboard_id": {"type": "integer"},
                "title": {"type": "string"},
                "field": {"type": "string", "description": "Data field to aggregate"},
                "aggregation": {"type": "string", "enum": ["count", "sum", "avg", "min", "max"]},
                "label": {"type": "string"},
                "unit": {"type": "string"},
                "position_x": {"type": "integer"},
                "position_y": {"type": "integer"},
            },
            "required": ["dashboard_id", "title", "field"],
        },
    },
    {
        "name": "add_line_chart",
        "description": "Add a line chart widget.",
        "parameters": {
            "type": "object",
            "properties": {
                "dashboard_id": {"type": "integer"},
                "title": {"type": "string"},
                "x_field": {"type": "string"},
                "y_field": {"type": "string"},
                "label": {"type": "string"},
                "color": {"type": "string"},
                "position_x": {"type": "integer"},
                "position_y": {"type": "integer"},
                "width": {"type": "integer"},
                "height": {"type": "integer"},
            },
            "required": ["dashboard_id", "title", "x_field", "y_field"],
        },
    },
    {
        "name": "add_bar_chart",
        "description": "Add a bar chart widget.",
        "parameters": {
            "type": "object",
            "properties": {
                "dashboard_id": {"type": "integer"},
                "title": {"type": "string"},
                "x_field": {"type": "string"},
                "y_field": {"type": "string"},
                "label": {"type": "string"},
                "color": {"type": "string"},
                "position_x": {"type": "integer"},
                "position_y": {"type": "integer"},
                "width": {"type": "integer"},
                "height": {"type": "integer"},
            },
            "required": ["dashboard_id", "title", "x_field", "y_field"],
        },
    },
    {
        "name": "add_table",
        "description": "Add a data table widget.",
        "parameters": {
            "type": "object",
            "properties": {
                "dashboard_id": {"type": "integer"},
                "title": {"type": "string"},
                "fields": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer"},
                "order_by": {"type": "string"},
                "order_dir": {"type": "string", "enum": ["asc", "desc"]},
                "position_x": {"type": "integer"},
                "position_y": {"type": "integer"},
                "width": {"type": "integer"},
                "height": {"type": "integer"},
            },
            "required": ["dashboard_id", "title", "fields"],
        },
    },
    {
        "name": "add_score_distribution",
        "description": "Add a score distribution histogram widget.",
        "parameters": {
            "type": "object",
            "properties": {
                "dashboard_id": {"type": "integer"},
                "title": {"type": "string"},
                "bins": {"type": "integer"},
                "label": {"type": "string"},
                "position_x": {"type": "integer"},
                "position_y": {"type": "integer"},
                "width": {"type": "integer"},
                "height": {"type": "integer"},
            },
            "required": ["dashboard_id", "title"],
        },
    },
    {
        "name": "update_widget",
        "description": "Update an existing widget's title, config, or position.",
        "parameters": {
            "type": "object",
            "properties": {
                "dashboard_id": {"type": "integer"},
                "widget_id": {"type": "integer"},
                "title": {"type": "string"},
                "config": {"type": "object"},
                "position_x": {"type": "integer"},
                "position_y": {"type": "integer"},
                "width": {"type": "integer"},
                "height": {"type": "integer"},
            },
            "required": ["dashboard_id", "widget_id"],
        },
    },
    {
        "name": "get_widget",
        "description": "Get the current config of a widget.",
        "parameters": {
            "type": "object",
            "properties": {
                "dashboard_id": {"type": "integer"},
                "widget_id": {"type": "integer"},
            },
            "required": ["dashboard_id", "widget_id"],
        },
    },
]

TOOL_HANDLERS = {
    "add_metric_card": add_metric_card,
    "add_line_chart": add_line_chart,
    "add_bar_chart": add_bar_chart,
    "add_table": add_table,
    "add_score_distribution": add_score_distribution,
    "update_widget": update_widget,
    "get_widget": get_widget,
}
