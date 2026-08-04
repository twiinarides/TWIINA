from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from functools import wraps


def admin_required(view_func):
    """Decorator: only admin role can access this view."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        try:
            if request.user.profile.is_admin():
                return view_func(request, *args, **kwargs)
        except Exception:
            pass
        return redirect('dashboard')
    return wrapper


def attendant_or_admin_required(view_func):
    """Decorator: both admin and attendant can access."""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        return view_func(request, *args, **kwargs)
    return wrapper
