"""Decorators for safe UI callbacks and tasks."""
from __future__ import annotations

import functools
import logging
from typing import Callable, Optional, TypeVar

import discord

from core.errors.interactions import safe_reply
from core.errors.logging import log_exception
from core.errors.messages import external_service_message, user_message_for

F = TypeVar("F", bound=Callable)


def safe_interaction(
    logger: logging.Logger,
    *,
    bot_name: str | None = None,
    user_message: str | None = None,
    component: str | None = None,
) -> Callable[[F], F]:
    """Wrap a view/modal callback: log failures and reply ephemerally."""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(self, interaction: discord.Interaction, *args, **kwargs):
            try:
                return await func(self, interaction, *args, **kwargs)
            except Exception as exc:
                msg = user_message or external_service_message(exc)
                log_exception(
                    logger,
                    exc,
                    bot_name=bot_name,
                    interaction=interaction,
                    component=component or func.__name__,
                )
                await safe_reply(interaction, content=f"`❌` {msg}", ephemeral=True)

        return wrapper  # type: ignore

    return decorator


def safe_task(
    logger: logging.Logger,
    action_name: str,
    *,
    bot_name: str | None = None,
    log_success: bool = False,
) -> Callable[[F], F]:
    """Like core @task but logs with exc_info on failure."""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            import time

            start = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                elapsed = round(time.perf_counter() - start, 2)
                if elapsed > 3:
                    logger.warning(
                        f"{action_name} took {elapsed}s"
                        + (f" [{bot_name}]" if bot_name else "")
                    )
                elif log_success:
                    logger.info(
                        f"{action_name} completed in {elapsed}s"
                        + (f" [{bot_name}]" if bot_name else "")
                    )
                return result
            except Exception as exc:
                log_exception(
                    logger,
                    exc,
                    bot_name=bot_name,
                    component=action_name,
                    extra={"elapsed_s": round(time.perf_counter() - start, 2)},
                )
                raise

        return wrapper  # type: ignore

    return decorator
