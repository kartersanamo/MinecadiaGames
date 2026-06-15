"""Process and Discord connection liveness monitoring.

The asyncio event loop can freeze while the process stays alive (no logs, no chat
games, bot appears offline). In-process task monitors cannot recover from that
because they share the same loop. A background thread watches a monotonic heartbeat
updated by a lightweight asyncio task and force-exits so run.sh can restart the bot.
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from typing import Optional

from discord.ext import commands

HEARTBEAT_INTERVAL = 30
STALE_THRESHOLD = 180
WATCHDOG_CHECK_INTERVAL = 30
DISCONNECT_RESTART_THRESHOLD = 300
GATEWAY_CHECK_INTERVAL = 120
GATEWAY_FAILURE_THRESHOLD = 3

_last_heartbeat = time.monotonic()
_heartbeat_lock = threading.Lock()
_watchdog_started = False
_disconnected_at: Optional[float] = None
_gateway_failures = 0
_liveness_task: Optional[asyncio.Task] = None


def touch_heartbeat() -> None:
    global _last_heartbeat
    with _heartbeat_lock:
        _last_heartbeat = time.monotonic()


def stale_seconds() -> float:
    with _heartbeat_lock:
        return time.monotonic() - _last_heartbeat


def mark_disconnected() -> None:
    global _disconnected_at
    if _disconnected_at is None:
        _disconnected_at = time.time()


def mark_connected() -> None:
    global _disconnected_at, _gateway_failures
    _disconnected_at = None
    _gateway_failures = 0


def _force_restart(log: logging.Logger, bot_name: str, reason: str) -> None:
    log.critical("[%s] %s — exiting for restart", bot_name, reason)
    os._exit(1)


def _watchdog_thread(log: logging.Logger, bot_name: str) -> None:
    while True:
        time.sleep(WATCHDOG_CHECK_INTERVAL)
        stale = stale_seconds()
        if stale > STALE_THRESHOLD:
            _force_restart(
                log,
                bot_name,
                f"Event loop watchdog: no heartbeat for {stale:.0f}s",
            )


def _start_thread_watchdog(log: logging.Logger, bot_name: str) -> None:
    global _watchdog_started
    if _watchdog_started:
        return
    _watchdog_started = True
    touch_heartbeat()
    thread = threading.Thread(
        target=_watchdog_thread,
        args=(log, bot_name),
        name=f"{bot_name}-watchdog",
        daemon=True,
    )
    thread.start()
    log.info("[%s] Event loop watchdog started (stale threshold=%ss)", bot_name, STALE_THRESHOLD)


async def _verify_gateway(bot: commands.Bot, log: logging.Logger, bot_name: str) -> None:
    global _gateway_failures

    guild_id = None
    try:
        guild_id = bot.config.get("config", "GUILD_ID")  # type: ignore[attr-defined]
    except Exception:
        pass

    if not guild_id:
        return

    try:
        guild = bot.get_guild(int(guild_id))
        if guild is None:
            await asyncio.wait_for(bot.fetch_guild(int(guild_id)), timeout=15.0)
        _gateway_failures = 0
    except Exception as exc:
        _gateway_failures += 1
        log.warning(
            "[%s] Gateway health check failed (%s/%s): %s",
            bot_name,
            _gateway_failures,
            GATEWAY_FAILURE_THRESHOLD,
            exc,
        )
        if _gateway_failures >= GATEWAY_FAILURE_THRESHOLD:
            _force_restart(
                log,
                bot_name,
                f"Gateway health check failed {_gateway_failures} times",
            )


async def _liveness_loop(bot: commands.Bot, log: logging.Logger, bot_name: str) -> None:
    global _disconnected_at
    last_gateway_check = 0.0

    while not bot.is_closed():
        touch_heartbeat()

        if bot.is_ready():
            _disconnected_at = None

            ws = getattr(bot, "ws", None)
            if ws is not None and getattr(ws, "closed", False):
                _force_restart(
                    log,
                    bot_name,
                    "WebSocket closed while bot reports ready",
                )

            now = time.monotonic()
            if now - last_gateway_check >= GATEWAY_CHECK_INTERVAL:
                last_gateway_check = now
                await _verify_gateway(bot, log, bot_name)
        else:
            if _disconnected_at is None:
                _disconnected_at = time.time()
            elif time.time() - _disconnected_at > DISCONNECT_RESTART_THRESHOLD:
                _force_restart(
                    log,
                    bot_name,
                    f"Disconnected for {time.time() - _disconnected_at:.0f}s without reconnect",
                )

        await asyncio.sleep(HEARTBEAT_INTERVAL)


async def start_liveness_monitor(
    bot: commands.Bot,
    *,
    log: logging.Logger,
    bot_name: str,
) -> None:
    """Start thread watchdog and asyncio liveness checks."""
    global _liveness_task

    _start_thread_watchdog(log, bot_name)

    if _liveness_task is not None and not _liveness_task.done():
        return

    _liveness_task = asyncio.create_task(_liveness_loop(bot, log, bot_name))
