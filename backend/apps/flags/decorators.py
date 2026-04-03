from functools import wraps

from django.http import Http404

from .utils import is_flag_active


def require_flag(flag_name: str):
    """
    View decorator that returns 404 if the named feature flag is not active
    for the requesting user.

    Usage::

        @require_flag("my-feature")
        def my_view(request):
            ...
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not is_flag_active(flag_name, request.user):
                raise Http404
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
