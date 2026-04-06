"""
Poll handler registry for the centralized front-end poller.

Each app registers handlers for its own watcher types.  The poll view
in core/views.py dispatches incoming watcher requests through this
registry so the core app stays decoupled from domain logic.

Usage
-----
In your app's poll_handlers.py::

    from apps.core.poll_handlers import register

    @register("my_watcher_type")
    def handle_my_watcher(request, watcher_id, params, target):
        # returns a directive dict or None
        return {
            "watcher_id": watcher_id,
            "url": "/some/endpoint/",   # frontend fetches this and swaps into target
            "target": target,
            "done": False,
        }

Register from your AppConfig.ready()::

    def ready(self):
        import apps.myapp.poll_handlers  # noqa: F401

Directive schema
----------------
Each handler must return either None (skip / no action) or a dict:

    {
        "watcher_id": str,          # echoed back so the client knows which watcher
        "url": str | None,          # if set: client fetches this and swaps into target
        "target": str,              # CSS selector for the swap target
        "done": bool,               # True → client stops watching after this tick
    }
"""

_registry: dict[str, callable] = {}


def register(watcher_type: str):
    """Decorator that registers a handler for a watcher type."""

    def decorator(fn):
        _registry[watcher_type] = fn
        return fn

    return decorator


def dispatch(watcher_type: str, request, watcher_id: str, params: dict, target: str):
    """
    Call the registered handler for *watcher_type*.

    Returns a directive dict, or a default "done" directive if no handler
    is registered for the type.
    """
    handler = _registry.get(watcher_type)
    if handler is None:
        return {"watcher_id": watcher_id, "url": None, "target": target, "done": True}
    return handler(request, watcher_id, params, target)
