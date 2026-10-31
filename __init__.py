"""Native backend-owned handoff command with optional origin-window context."""
import re

_USAGE = "Usage: /handoff-continue [status|cancel]"
_PROFILE = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
_SESSION = re.compile(r"[a-zA-Z0-9_-]{1,160}")
_WINDOW = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")
_UNSET = object()


def create_handler(service, get_env, profile_name="default"):
    """Capture explicit gateway context before any background work starts.

    Modern local dispatch supplies a SessionSource, not Desktop environment
    variables. Older Desktop dispatch is retained via the bound env fallback.
    Explicit empty values never fall back to a possibly unrelated ambient ID.
    """
    def handle(raw_args, *, source=None, platform=_UNSET,
               session_id=_UNSET, session_key=_UNSET, desktop_window_id=None):
        args = raw_args.strip().split()
        if args not in ([], ["status"], ["cancel"]):
            return _USAGE
        if desktop_window_id is not None and (
                not isinstance(desktop_window_id, str) or not _WINDOW.fullmatch(desktop_window_id)):
            return "Handoff refused: invalid Desktop window identity."
        surface = get_env("HERMES_SESSION_SOURCE", "") if platform is _UNSET else platform
        if surface not in ("local", "desktop"):
            return "Use /handoff-continue in an existing local Desktop session."
        if source is not None:
            stored = getattr(source, "chat_id", "")
            profile = getattr(source, "profile", None) or profile_name
        else:
            profile = get_env("HERMES_SESSION_PROFILE", "")
            stored = (session_id if session_id is not _UNSET else
                      session_key if session_key is not _UNSET else
                      get_env("HERMES_SESSION_KEY", ""))
        if (not isinstance(stored, str) or not _SESSION.fullmatch(stored)
                or not isinstance(profile, str) or not _PROFILE.fullmatch(profile)
                or profile != profile_name):
            return "Handoff refused: local session identity or owning profile is missing/mismatched."
        try:
            context = {"stored_id": stored, "profile": profile}
            if desktop_window_id is not None:
                context["desktop_window_id"] = desktop_window_id
            return service.handle(args[0] if args else "start", **context)
        except Exception as exc:
            # Never route an exception back into model/skill fallback dispatch.
            return f"Handoff backend refused the request ({type(exc).__name__}); inspect backend status/logs. No automatic retry."
    return handle


def register(ctx):
    from pathlib import Path
    from hermes_constants import get_hermes_home, profile_name_for_home
    from .backend import BackendService

    home = Path(get_hermes_home()).resolve()
    profile = profile_name_for_home(home) or "default"
    service = BackendService(home, profile)

    def get_env(key, default=""):
        from gateway.session_context import get_session_env
        return get_session_env(key, default)

    ctx.on_unload(service.close)
    ctx.register_command(
        "handoff-continue", handler=create_handler(service, get_env, profile),
        description="Write a verified handoff and continue in a fresh session entirely on the backend",
        args_hint="[status|cancel]",
    )
