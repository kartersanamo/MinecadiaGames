"""
Shared HTTP client for posting audit logs to MinecadiaManagement.

Copy this file into other bots (Utilities, Games, etc.) or import via shared path.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import aiohttp

_log = logging.getLogger("management_log_client")


def _url() -> str | None:
    return os.environ.get("MANAGEMENT_LOG_HTTP_URL") or os.environ.get("MANAGEMENT_LOG_API_URL")


def _token() -> str | None:
    return os.environ.get("MANAGEMENT_LOG_API_SECRET")


async def post_audit_log(
    *,
    event_type: str,
    title: str,
    summary: str | None = None,
    actor_id: int | None = None,
    target_id: int | None = None,
    channel_id: int | None = None,
    guild_id: int | None = None,
    severity: str = "info",
    source_bot: str = "External",
    metadata: dict[str, Any] | None = None,
    route_admin: bool = False,
    immediate: bool = False,
) -> str | None:
    """Post a log entry. Returns event_id on success, None if disabled or failed."""
    url = _url()
    token = _token()
    if not url or not token:
        _log.debug("Management log HTTP not configured")
        return None

    payload: dict[str, Any] = {
        "event_type": event_type,
        "title": title,
        "summary": summary,
        "actor_id": actor_id,
        "target_id": target_id,
        "channel_id": channel_id,
        "guild_id": guild_id,
        "severity": severity,
        "source_bot": source_bot,
        "metadata": metadata or {},
        "route_admin": route_admin,
        "immediate": immediate,
    }

    headers = {"X-Log-Token": token, "Content-Type": "application/json"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    _log.warning("Management log HTTP %s: %s", resp.status, text[:200])
                    return None
                data = await resp.json()
                return data.get("event_id")
    except Exception as exc:
        _log.warning("Management log HTTP failed: %s", exc)
        return None
