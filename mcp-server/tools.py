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
    if not resp.is_success:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text[:200]
        raise RuntimeError(f"HTTP {resp.status_code}: {detail}")
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
        "description": (
            "Add a metric card widget showing a single aggregated value. "
            "Use field='prediction_count' for predictions, 'execution_count' for runs, 'score' for scores. "
            "Use aggregation='count' by default unless the user specifies sum/avg/min/max."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Widget title, e.g. 'Total Predictions'",
                },
                "field": {
                    "type": "string",
                    "description": "Field to aggregate, e.g. 'prediction_count', 'execution_count', 'score'",
                },
                "aggregation": {
                    "type": "string",
                    "enum": ["count", "sum", "avg", "min", "max"],
                    "description": "Default: count",
                },
                "label": {"type": "string", "description": "Optional display label"},
                "unit": {"type": "string", "description": "Optional unit suffix, e.g. '%'"},
            },
            "required": ["title", "field"],
        },
    },
    {
        "name": "add_line_chart",
        "description": (
            "Add a line chart widget showing a trend over time. "
            "Use x_field='date' for time-based charts. "
            "Use y_field='prediction_count', 'execution_count', or 'score' based on what the user wants."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Widget title, e.g. 'Predictions Over Time'",
                },
                "x_field": {"type": "string", "description": "X-axis field, typically 'date'"},
                "y_field": {
                    "type": "string",
                    "description": "Y-axis field, e.g. 'prediction_count', 'score'",
                },
                "label": {"type": "string", "description": "Optional series label"},
                "color": {"type": "string", "description": "Hex color, default '#4f46e5'"},
            },
            "required": ["title", "x_field", "y_field"],
        },
    },
    {
        "name": "add_bar_chart",
        "description": (
            "Add a bar chart widget. "
            "Use x_field='date' for charts grouped by day. "
            "Use y_field='prediction_count', 'execution_count', or 'score' based on what the user wants."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Widget title, e.g. 'Predictions by Day'",
                },
                "x_field": {"type": "string", "description": "X-axis field, e.g. 'date'"},
                "y_field": {
                    "type": "string",
                    "description": "Y-axis field, e.g. 'prediction_count'",
                },
                "label": {"type": "string", "description": "Optional series label"},
                "color": {"type": "string", "description": "Hex color, default '#4f46e5'"},
            },
            "required": ["title", "x_field", "y_field"],
        },
    },
    {
        "name": "add_table",
        "description": "Add a data table widget showing rows of data.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Widget title"},
                "fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of field names to display, e.g. ['date', 'prediction_count', 'score']",
                },
                "limit": {"type": "integer", "description": "Max rows to show, default 10"},
                "order_by": {"type": "string", "description": "Field to sort by"},
                "order_dir": {
                    "type": "string",
                    "enum": ["asc", "desc"],
                    "description": "Sort direction, default 'desc'",
                },
            },
            "required": ["title", "fields"],
        },
    },
    {
        "name": "add_score_distribution",
        "description": "Add a histogram showing the distribution of scores.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Widget title, e.g. 'Score Distribution'",
                },
                "bins": {"type": "integer", "description": "Number of histogram bins, default 10"},
                "label": {"type": "string", "description": "Optional label"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "update_widget",
        "description": "Update an existing widget's title, config, or position.",
        "parameters": {
            "type": "object",
            "properties": {
                "widget_id": {"type": "integer", "description": "ID of the widget to update"},
                "title": {"type": "string"},
                "config": {"type": "object"},
                "position_x": {"type": "integer"},
                "position_y": {"type": "integer"},
                "width": {"type": "integer"},
                "height": {"type": "integer"},
            },
            "required": ["widget_id"],
        },
    },
    {
        "name": "get_widget",
        "description": "Get the current config of a widget by its ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "widget_id": {"type": "integer", "description": "ID of the widget to retrieve"},
            },
            "required": ["widget_id"],
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
