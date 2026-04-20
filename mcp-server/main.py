"""
MCP server — FastAPI application that:
 1. Accepts chat requests from Django (authenticated by user's API key)
 2. Dispatches to Anthropic or OpenAI-compatible (Llama) with tool use
 3. Calls Django internal APIs to mutate dashboard state
 4. Streams SSE tokens back to Django, which proxies them to the browser
 5. Reports token consumption back to Django at the end of each turn
"""

import json
import logging
import os
from collections.abc import AsyncIterator

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from tools import TOOL_HANDLERS, TOOL_SCHEMAS

logger = logging.getLogger(__name__)

app = FastAPI(title="MCP Dashboard Builder", version="1.0.0")

DJANGO_URL = os.environ.get("DJANGO_INTERNAL_URL", "http://web:8000")
MCP_INTERNAL_SECRET = os.environ.get("MCP_INTERNAL_SECRET", "")

SYSTEM_PROMPT = """You are a dashboard widget builder. Call the tools immediately when asked. Never ask for clarification.

RULES:
1. Call a tool right away. Do not ask questions first.
2. Use these field name defaults:
   - date/time/day → x_field="date"
   - predictions/count → y_field="prediction_count"
   - executions/runs → y_field="execution_count"
   - score/accuracy → y_field="score"
3. After the tool succeeds, reply with one short sentence confirming what was added.
4. If the tool fails, say so in one sentence.

EXAMPLES:
User: "add a bar chart of predictions by day"
→ Call add_bar_chart(title="Predictions by Day", x_field="date", y_field="prediction_count")

User: "show total executions"
→ Call add_metric_card(title="Total Executions", field="execution_count", aggregation="count")

User: "line chart of scores over time"
→ Call add_line_chart(title="Scores Over Time", x_field="date", y_field="score")"""


class ChatRequest(BaseModel):
    message: str
    session_id: int
    provider: str  # "ANTHROPIC" or "LLAMA_OPENAI"
    base_url: str | None = None
    user_id: int
    dashboard_id: int | None = None


def _update_session_tokens(session_id: int, tokens_used: int) -> None:
    """Fire-and-forget token update to Django."""
    try:
        httpx.post(
            f"{DJANGO_URL}/internal/mcp/session/tokens/",
            json={"session_id": session_id, "tokens_used": tokens_used},
            headers={
                "Authorization": f"Bearer {MCP_INTERNAL_SECRET}",
                "Content-Type": "application/json",
            },
            timeout=5.0,
        )
    except Exception:
        logger.warning("Failed to update session tokens for session %s", session_id)


async def _stream_anthropic(
    api_key: str,
    messages: list,
    session_id: int,
    dashboard_id: int | None,
) -> AsyncIterator[str]:
    """Stream a response from Anthropic, executing tool calls inline."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    total_tokens = 0

    try:
        while True:
            tool_results = []
            assistant_text = ""

            with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=messages,
                tools=TOOL_SCHEMAS,  # type: ignore[arg-type]
            ) as stream:
                for event in stream:
                    event_type = type(event).__name__

                    if event_type == "RawContentBlockDeltaEvent":
                        delta = event.delta
                        if hasattr(delta, "text"):
                            assistant_text += delta.text
                            yield f"data: {json.dumps({'token': delta.text})}\n\n"

                    elif event_type == "RawMessageStopEvent":
                        pass

                final = stream.get_final_message()
                total_tokens = final.usage.input_tokens + final.usage.output_tokens
                yield f"data: {json.dumps({'tokens_used': total_tokens, 'session_id': session_id})}\n\n"

                # Process tool use blocks
                for block in final.content:
                    if block.type == "tool_use":
                        tool_name = block.name
                        tool_input = block.input

                        if dashboard_id:
                            tool_input["dashboard_id"] = dashboard_id

                        handler = TOOL_HANDLERS.get(tool_name)
                        if handler:
                            try:
                                result = handler(**tool_input)
                                tool_results.append(
                                    {
                                        "type": "tool_result",
                                        "tool_use_id": block.id,
                                        "content": json.dumps(result),
                                    }
                                )
                                # Signal the browser to reload the widget iframe
                                yield f"data: {json.dumps({'reload_widgets': True})}\n\n"
                            except Exception as exc:
                                tool_results.append(
                                    {
                                        "type": "tool_result",
                                        "tool_use_id": block.id,
                                        "content": f"Error: {exc}",
                                        "is_error": True,
                                    }
                                )
                        else:
                            tool_results.append(
                                {
                                    "type": "tool_result",
                                    "tool_use_id": block.id,
                                    "content": "Unknown tool",
                                    "is_error": True,
                                }
                            )

                if final.stop_reason == "tool_use":
                    messages = messages + [
                        {"role": "assistant", "content": final.content},
                        {"role": "user", "content": tool_results},
                    ]
                else:
                    break
    except Exception:
        logger.exception("Error in _stream_anthropic for session %s", session_id)
        yield f"data: {json.dumps({'error': 'stream_error'})}\n\n"
    finally:
        _update_session_tokens(session_id, total_tokens)


async def _stream_openai(
    api_key: str,
    base_url: str,
    messages: list,
    session_id: int,
    dashboard_id: int | None,
) -> AsyncIterator[str]:
    """Stream a response from an OpenAI-compatible endpoint (Llama/Ollama)."""
    import openai

    client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
    total_tokens = 0

    # Convert Anthropic tool schema format to OpenAI format
    openai_tools = [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            },
        }
        for t in TOOL_SCHEMAS
    ]

    openai_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages

    # Discover the loaded model — LM Studio requires the real identifier
    try:
        models_response = await client.models.list()
        model_id = models_response.data[0].id if models_response.data else "local-model"
    except Exception:
        model_id = "local-model"

    try:
        while True:
            tool_calls_pending = []
            # Reconstruct the full assistant message so it can be appended to
            # history before tool results — OpenAI format requires this ordering.
            assistant_tool_calls = []
            assistant_content = ""

            async with await client.chat.completions.create(
                model=model_id,
                messages=openai_messages,
                tools=openai_tools,
                stream=True,
            ) as stream:
                async for chunk in stream:
                    choice = chunk.choices[0] if chunk.choices else None
                    if choice is None:
                        continue

                    delta = choice.delta
                    if delta.content:
                        assistant_content += delta.content
                        yield f"data: {json.dumps({'token': delta.content})}\n\n"

                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            while len(tool_calls_pending) <= tc.index:
                                tool_calls_pending.append({"id": "", "name": "", "arguments": ""})
                                assistant_tool_calls.append(
                                    {
                                        "id": "",
                                        "type": "function",
                                        "function": {"name": "", "arguments": ""},
                                    }
                                )
                            if tc.id:
                                tool_calls_pending[tc.index]["id"] = tc.id
                                assistant_tool_calls[tc.index]["id"] = tc.id
                            if tc.function and tc.function.name:
                                tool_calls_pending[tc.index]["name"] = tc.function.name
                                assistant_tool_calls[tc.index]["function"]["name"] = (
                                    tc.function.name
                                )
                            if tc.function and tc.function.arguments:
                                tool_calls_pending[tc.index]["arguments"] += tc.function.arguments
                                assistant_tool_calls[tc.index]["function"]["arguments"] += (
                                    tc.function.arguments
                                )

                    if chunk.usage:
                        total_tokens = chunk.usage.total_tokens
                        yield f"data: {json.dumps({'tokens_used': total_tokens, 'session_id': session_id})}\n\n"

                    if choice.finish_reason == "stop":
                        break

            if tool_calls_pending:
                # Build the assistant message that produced these tool calls
                assistant_msg: dict = {"role": "assistant"}
                if assistant_content:
                    assistant_msg["content"] = assistant_content
                if assistant_tool_calls:
                    assistant_msg["tool_calls"] = assistant_tool_calls

                tool_result_messages = [assistant_msg]
                for tc in tool_calls_pending:
                    tool_name = tc["name"]
                    try:
                        tool_input = json.loads(tc["arguments"])
                    except json.JSONDecodeError:
                        tool_input = {}

                    if dashboard_id:
                        tool_input["dashboard_id"] = dashboard_id

                    handler = TOOL_HANDLERS.get(tool_name)
                    if handler:
                        try:
                            result = handler(**tool_input)
                            content = json.dumps(result)
                            yield f"data: {json.dumps({'reload_widgets': True})}\n\n"
                        except Exception as exc:
                            content = f"Error: {exc}"
                    else:
                        content = "Unknown tool"

                    tool_result_messages.append(
                        {"role": "tool", "tool_call_id": tc["id"], "content": content}
                    )

                openai_messages = openai_messages + tool_result_messages
            else:
                break
    except Exception:
        logger.exception("Error in _stream_openai for session %s", session_id)
        yield f"data: {json.dumps({'error': 'stream_error'})}\n\n"
    finally:
        _update_session_tokens(session_id, total_tokens)


@app.post("/chat/")
async def chat(
    request: Request,
    authorization: str = Header(...),
    x_mcp_internal_secret: str = Header("", alias="x-mcp-internal-secret"),
    x_mcp_user_id: str = Header("", alias="x-mcp-user-id"),
    x_mcp_session_id: str = Header("", alias="x-mcp-session-id"),
) -> StreamingResponse:
    """
    Receive a chat turn from Django and stream SSE back.
    The Authorization header carries the user's plaintext API key.
    """
    # Verify the internal secret to confirm this came from Django
    if not MCP_INTERNAL_SECRET or x_mcp_internal_secret != MCP_INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing API key")

    api_key = authorization[len("Bearer ") :]

    body = await request.json()
    chat_req = ChatRequest(**body)

    # Build message history — for now, single-turn (stateless per request)
    # A production implementation would persist conversation history in Redis
    messages = [{"role": "user", "content": chat_req.message}]

    if chat_req.provider == "ANTHROPIC":
        stream = _stream_anthropic(
            api_key=api_key,
            messages=messages,
            session_id=chat_req.session_id,
            dashboard_id=chat_req.dashboard_id,
        )
    elif chat_req.provider == "LLAMA_OPENAI":
        if not chat_req.base_url:
            raise HTTPException(status_code=400, detail="base_url required for LLAMA_OPENAI")
        stream = _stream_openai(
            api_key=api_key,
            base_url=chat_req.base_url,
            messages=messages,
            session_id=chat_req.session_id,
            dashboard_id=chat_req.dashboard_id,
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {chat_req.provider}")

    return StreamingResponse(stream, media_type="text/event-stream")


@app.get("/health/")
async def health() -> dict:
    return {"status": "ok"}
