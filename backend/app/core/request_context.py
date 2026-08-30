"""
Exposes the current request's correlation ID (set by RequestIdMiddleware,
see app/core/middleware.py — this is not a second ID system) to code that
doesn't have direct access to the Request object, most notably the service
layer when it dispatches an audit log write.

A contextvar rather than passing `request_id` as an explicit parameter down
every router -> service -> repository call chain: that would mean touching
the signature of every function in the write path for a field most of them
have no other use for. The contextvar is only valid within the web process
handling the request — see write_audit_log_task's docstring for why the
value has to be read and captured *before* `.delay()`, not inside the task.
"""
import contextvars

_request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)
_user_agent_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "user_agent", default=None
)


def set_request_context(request_id: str | None, user_agent: str | None = None) -> None:
    _request_id_var.set(request_id)
    _user_agent_var.set(user_agent)


def get_current_request_id() -> str | None:
    return _request_id_var.get()


def get_current_user_agent() -> str | None:
    return _user_agent_var.get()
