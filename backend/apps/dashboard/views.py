import json
import logging

import altair as alt
import httpx
import polars as pl
from apps.accounts.models import UserApiKey
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count
from django.db.models.functions import TruncDate
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import DashboardWidget, McpSession, UserDashboard

logger = logging.getLogger(__name__)

# ── helpers ───────────────────────────────────────────────────────────────────


def _require_internal_token(request):
    """Return None if the Bearer token is valid, else an HttpResponse 401/403."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return HttpResponse(status=401)
    token = auth[len("Bearer ") :]
    expected = settings.MCP_INTERNAL_SECRET
    if not expected or token != expected:
        return HttpResponse(status=403)
    return None


def _active_key(user):
    """Return the first active UserApiKey for user, or None."""
    return UserApiKey.objects.filter(user=user, is_active=True).first()


# ── dashboard main views ──────────────────────────────────────────────────────


@login_required
@require_http_methods(["GET"])
def dashboard(request):
    """Main conversational dashboard page."""
    api_key = _active_key(request.user)
    user_dashboard = UserDashboard.get_or_create_active(request.user)

    # Current open session (not exhausted and not ended)
    session = (
        McpSession.objects.filter(
            user=request.user,
            ended_at__isnull=True,
        )
        .order_by("-started_at")
        .first()
    )

    context = {
        "api_key": api_key,
        "dashboard": user_dashboard,
        "session": session,
        "active_page": "my_dashboard",
    }
    return render(request, "dashboard/dashboard.html", context)


def _build_altair_spec(widget: DashboardWidget) -> dict | None:
    """
    Build an Altair Vega-Lite spec dict for a widget.
    Returns None when the widget type doesn't produce a chart or has no data.
    """
    from apps.flows.models import FlowExecution, PredictionResult

    config = widget.config
    wtype = widget.widget_type
    color = config.get("color", "#4f46e5")

    # ── time-series bar / line ────────────────────────────────────────────────
    if wtype in ("LINE_CHART", "BAR_CHART"):
        y_field = config.get("y_field", "execution_count")
        y_label = config.get("label") or y_field.replace("_", " ").title()

        if y_field in ("execution_count", "count"):
            rows = list(
                FlowExecution.objects.annotate(date=TruncDate("created_at"))
                .values("date")
                .annotate(value=Count("id"))
                .order_by("date")[:60]
            )
        elif y_field == "prediction_count":
            rows = list(
                PredictionResult.objects.annotate(date=TruncDate("scored_at"))
                .values("date")
                .annotate(value=Count("id"))
                .order_by("date")[:60]
            )
        elif y_field == "score":
            rows = list(
                PredictionResult.objects.annotate(date=TruncDate("scored_at"))
                .values("date")
                .annotate(value=Avg("score"))
                .order_by("date")[:60]
            )
        else:
            rows = []

        if not rows:
            return None

        df = pl.DataFrame(
            {
                "date": [str(r["date"]) for r in rows],
                "value": [float(r["value"]) if r["value"] is not None else 0.0 for r in rows],
            }
        )

        base = alt.Chart(df).encode(
            x=alt.X("date:T", axis=alt.Axis(labelAngle=-30, format="%b %d"), title=None),
            y=alt.Y("value:Q", title=y_label),
        )
        if wtype == "BAR_CHART":
            chart = base.mark_bar(color=color)
        else:
            chart = base.mark_line(color=color, point=alt.OverlayMarkDef(color=color, size=30))

        return chart.properties(width=360, height=160).to_dict()

    # ── metric card ───────────────────────────────────────────────────────────
    if wtype == "METRIC_CARD":
        field = config.get("field", "execution_count")

        if field in ("execution_count", "count"):
            result = FlowExecution.objects.aggregate(v=Count("id"))
        elif field == "prediction_count":
            result = PredictionResult.objects.aggregate(v=Count("id"))
        elif field == "score":
            result = PredictionResult.objects.aggregate(v=Avg("score"))
        else:
            result = {"v": 0}

        raw = result["v"]
        value = round(float(raw), 2) if raw is not None else 0
        # Metric cards don't use Altair — return a plain dict the template reads directly.
        return {"_metric": True, "value": value}

    # ── score distribution ────────────────────────────────────────────────────
    if wtype == "SCORE_DISTRIBUTION":
        scores = list(PredictionResult.objects.values_list("score", flat=True)[:2000])
        if not scores:
            return None

        df = pl.DataFrame({"score": [float(s) for s in scores]})
        chart = (
            alt.Chart(df)
            .mark_bar(color=color)
            .encode(
                x=alt.X("score:Q", bin=alt.Bin(maxbins=config.get("bins", 10)), title="Score"),
                y=alt.Y("count():Q", title="Count"),
            )
            .properties(width=360, height=160)
        )
        return chart.to_dict()

    return None


@login_required
@require_http_methods(["GET"])
def widget_grid(request):
    """HTMX partial: the user's active widget grid."""
    user_dashboard = UserDashboard.objects.filter(owner=request.user, is_active=True).first()
    widgets = []
    for w in user_dashboard.widgets.all() if user_dashboard else []:
        data = _build_altair_spec(w)
        widgets.append(
            {
                "widget": w,
                # Metric cards carry _metric flag; chart widgets carry a Vega-Lite spec.
                "metric_value": data.get("value") if data and data.get("_metric") else None,
                "vega_spec": json.dumps(data) if data and not data.get("_metric") else None,
            }
        )
    return render(
        request,
        "dashboard/partials/widget_grid.html",
        {"dashboard": user_dashboard, "widgets": widgets},
    )


# ── chat SSE endpoint ─────────────────────────────────────────────────────────


@login_required
@require_http_methods(["POST"])
def dashboard_chat(request):
    """
    Accepts a user message, opens or reuses an McpSession, proxies the request
    to the MCP server, and streams the response back as SSE.

    Expected POST body (JSON): {"message": "...", "session_id": <int|null>}
    """
    api_key = _active_key(request.user)
    if api_key is None:
        return JsonResponse({"error": "no_api_key"}, status=403)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "invalid_json"}, status=400)

    message = (body.get("message") or "").strip()
    if not message:
        return JsonResponse({"error": "empty_message"}, status=400)

    # Resolve or create session
    session_id = body.get("session_id")
    session = None
    if session_id:
        session = McpSession.objects.filter(
            pk=session_id, user=request.user, ended_at__isnull=True
        ).first()

    if session is None:
        profile = getattr(request.user, "profile", None)
        budget = (
            profile.mcp_token_budget
            if profile and profile.mcp_token_budget
            else settings.MCP_SESSION_TOKEN_BUDGET
        )
        session = McpSession.objects.create(
            user=request.user,
            user_api_key=api_key,
            tokens_used=0,
            tokens_budget=budget,
        )

    if session.is_exhausted:
        return JsonResponse({"error": "budget_exhausted", "session_id": session.pk}, status=429)

    # Decrypt the key in memory — never log it
    try:
        plain_key = api_key.get_key()
    except Exception:
        logger.exception("Failed to decrypt API key for user %s", request.user.pk)
        return JsonResponse({"error": "key_decrypt_failed"}, status=500)

    mcp_url = f"{settings.MCP_SERVER_URL}/chat/"
    payload = {
        "message": message,
        "session_id": session.pk,
        "provider": api_key.provider,
        "base_url": api_key.base_url or None,
        "user_id": request.user.pk,
        "dashboard_id": (
            UserDashboard.objects.filter(owner=request.user, is_active=True)
            .values_list("pk", flat=True)
            .first()
        ),
    }
    headers = {
        "Authorization": f"Bearer {plain_key}",
        "X-MCP-Internal-Secret": settings.MCP_INTERNAL_SECRET,
        "X-MCP-User-Id": str(request.user.pk),
        "X-MCP-Session-Id": str(session.pk),
        "Content-Type": "application/json",
    }

    token_budget = session.tokens_budget

    def _sse_generator():
        try:
            with httpx.stream(
                "POST",
                mcp_url,
                json=payload,
                headers=headers,
                timeout=120.0,
            ) as resp:
                if resp.status_code != 200:
                    yield f"data: {json.dumps({'error': 'mcp_error', 'status': resp.status_code})}\n\n"
                    return
                for line in resp.iter_lines():
                    if not line:
                        continue
                    # Augment token events with the budget so the browser can render the bar
                    if line.startswith("data: ") and '"tokens_used"' in line:
                        try:
                            event_data = json.loads(line[6:])
                            if "tokens_used" in event_data and "tokens_budget" not in event_data:
                                event_data["tokens_budget"] = token_budget
                                yield f"data: {json.dumps(event_data)}\n\n"
                                continue
                        except (json.JSONDecodeError, ValueError):
                            pass
                    yield f"{line}\n\n"
        except httpx.ConnectError:
            yield f"data: {json.dumps({'error': 'mcp_unavailable'})}\n\n"
        except httpx.RemoteProtocolError:
            logger.warning("MCP server closed connection mid-stream for session %s", session.pk)
            yield f"data: {json.dumps({'error': 'stream_error'})}\n\n"
        except Exception:
            logger.exception("SSE proxy error for session %s", session.pk)
            yield f"data: {json.dumps({'error': 'proxy_error'})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingHttpResponse(
        _sse_generator(),
        content_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@login_required
@require_http_methods(["POST"])
def session_reset(request):
    """End the current open session so the next chat starts a new budget window."""
    McpSession.objects.filter(user=request.user, ended_at__isnull=True).update(
        ended_at=timezone.now()
    )
    return HttpResponse(status=204)


# ── internal API — called by the MCP server ──────────────────────────────────


@csrf_exempt
@require_http_methods(["GET"])
def internal_widget_data(request, dashboard_id, widget_id):
    """
    MCP server calls this to fetch the current config/data for a widget.
    Authenticated by the shared MCP_INTERNAL_SECRET.
    """
    err = _require_internal_token(request)
    if err:
        return err

    dashboard = get_object_or_404(UserDashboard, pk=dashboard_id)
    widget = get_object_or_404(DashboardWidget, pk=widget_id, dashboard=dashboard)
    return JsonResponse(
        {
            "id": widget.pk,
            "widget_type": widget.widget_type,
            "title": widget.title,
            "config": widget.config,
            "position_x": widget.position_x,
            "position_y": widget.position_y,
            "width": widget.width,
            "height": widget.height,
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
def internal_widget_upsert(request, dashboard_id):
    """
    MCP server calls this to create or replace a widget on the dashboard.
    Body: JSON matching DashboardWidget fields.
    """
    err = _require_internal_token(request)
    if err:
        return err

    dashboard = get_object_or_404(UserDashboard, pk=dashboard_id)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "invalid_json"}, status=400)

    widget_id = data.get("id")
    if widget_id:
        widget = get_object_or_404(DashboardWidget, pk=widget_id, dashboard=dashboard)
    else:
        widget = DashboardWidget(dashboard=dashboard)

    widget.widget_type = data.get("widget_type", widget.widget_type)
    widget.title = data.get("title", widget.title)
    widget.config = data.get("config", widget.config)
    widget.position_x = data.get("position_x", widget.position_x)
    widget.position_y = data.get("position_y", widget.position_y)
    widget.width = data.get("width", widget.width)
    widget.height = data.get("height", widget.height)

    try:
        widget.full_clean()
    except Exception as exc:
        from django.core.exceptions import ValidationError

        if isinstance(exc, ValidationError):
            return JsonResponse({"error": exc.message_dict}, status=400)
        raise

    widget.save()
    return JsonResponse({"id": widget.pk}, status=200)


@csrf_exempt
@require_http_methods(["POST"])
def internal_session_token_update(request):
    """
    MCP server calls this to record tokens consumed by a session.
    Body: {"session_id": int, "tokens_used": int}
    """
    err = _require_internal_token(request)
    if err:
        return err

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "invalid_json"}, status=400)

    session = get_object_or_404(McpSession, pk=data.get("session_id"))
    session.tokens_used = data.get("tokens_used", session.tokens_used)
    if session.is_exhausted and session.ended_at is None:
        session.ended_at = timezone.now()
    session.save(update_fields=["tokens_used", "ended_at"])

    return JsonResponse(
        {
            "tokens_remaining": session.tokens_remaining,
            "is_exhausted": session.is_exhausted,
        }
    )
