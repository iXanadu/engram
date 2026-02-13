import os
import socket


def resolve_scope_and_user_id(
    scope: str | None = None, default_scope: str = "machine"
) -> tuple[str, str]:
    """Resolve a scope name to an engram (scope, user_id) tuple.

    Returns:
        (scope, user_id) tuple:
            machine  -> ("machine", hostname)
            shared   -> ("shared", "global")
            project  -> ("project", dirname)
            custom   -> (custom, custom)   passthrough
    """
    scope = scope or default_scope

    if scope == "machine":
        hostname = socket.gethostname().split(".")[0].lower()
        return ("machine", hostname)
    elif scope == "shared":
        return ("shared", "global")
    elif scope == "project":
        dirname = os.path.basename(os.getcwd())
        return ("project", dirname)
    else:
        return (scope, scope)
