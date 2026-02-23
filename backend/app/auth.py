from fastapi import Request
from .config import settings

def is_logged_in(request: Request) -> bool:
    return request.session.get("user") == settings.ADMIN_USER

def require_login(request: Request):
    if not is_logged_in(request):
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/login", status_code=302)
    return None
