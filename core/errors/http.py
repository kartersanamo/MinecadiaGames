"""HTTP error helpers for aiohttp dashboard APIs."""
from __future__ import annotations

import logging
from typing import Any, Callable, Awaitable

from aiohttp import web

from core.errors.logging import log_exception
from core.errors.messages import user_message_for


def json_error(message: str, status: int = 400, **extra: Any) -> web.Response:
    body: dict[str, Any] = {"error": message}
    body.update(extra)
    return web.json_response(body, status=status)


def route_wrapper(
    logger: logging.Logger,
    *,
    bot_name: str | None = None,
) -> Callable[
    [Callable[[web.Request], Awaitable[web.Response]]],
    Callable[[web.Request], Awaitable[web.Response]],
]:
    """Decorator for aiohttp handlers: catch exceptions and return JSON errors."""

    def decorator(
        handler: Callable[[web.Request], Awaitable[web.Response]],
    ) -> Callable[[web.Request], Awaitable[web.Response]]:
        async def wrapped(request: web.Request) -> web.Response:
            try:
                return await handler(request)
            except web.HTTPException:
                raise
            except Exception as exc:
                log_exception(logger, exc, bot_name=bot_name, component=request.path)
                return json_error(user_message_for(exc), status=500)

        return wrapped

    return decorator
