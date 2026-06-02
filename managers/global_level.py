"""Cumulative global level from end-of-month levels at each /wipe-levels."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING

from core.logging.setup import get_logger

if TYPE_CHECKING:
    from core.database.pool import DatabasePool

logger = get_logger("GlobalLevel")

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS leveling_global (
  user_id VARCHAR(32) NOT NULL PRIMARY KEY,
  global_level INT UNSIGNED NOT NULL DEFAULT 0,
  updated_at INT UNSIGNED NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


async def ensure_global_level_table(db: "DatabasePool") -> None:
    await db.execute(CREATE_TABLE_SQL)


async def archive_monthly_levels_to_global(
    db: "DatabasePool",
    *,
    month: str | None = None,
) -> int:
    """
    Add each user's current monthly `level` from `leveling` into `leveling_global`.
    Call immediately before resetting `leveling` on /wipe-levels.
    """
    await ensure_global_level_table(db)
    rows = await db.execute(
        "SELECT user_id, level FROM leveling WHERE CAST(level AS UNSIGNED) >= 1"
    )
    if not rows:
        logger.info("[GlobalLevel] No leveling rows to archive for %s", month or "wipe")
        return 0

    now = int(time.time())
    archived = 0
    for row in rows:
        uid = str(row["user_id"])
        month_level = max(1, int(row.get("level") or 1))
        await db.execute(
            """
            INSERT INTO leveling_global (user_id, global_level, updated_at)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
              global_level = global_level + %s,
              updated_at = %s
            """,
            (uid, month_level, now, month_level, now),
        )
        archived += 1

    logger.info(
        "[GlobalLevel] Archived %s users' month-end levels into global_level (%s)",
        archived,
        month or "wipe",
    )
    return archived


async def backfill_global_levels_from_winners(db: "DatabasePool") -> int:
    """
    One-time partial backfill: winners.json only stores top 10 per month.
    Skips if leveling_global already has rows.
    """
    await ensure_global_level_table(db)
    existing = await db.execute("SELECT COUNT(*) AS c FROM leveling_global")
    if existing and int(existing[0].get("c") or 0) > 0:
        return 0

    winners_path = (
        Path(__file__).parent.parent / "assets" / "Configs" / "winners.json"
    )
    if not winners_path.is_file():
        return 0

    with open(winners_path, encoding="utf-8") as f:
        data = json.load(f)

    months = data.get("Months") or {}
    now = int(time.time())
    updated = 0
    for _month, users in months.items():
        if not isinstance(users, dict):
            continue
        for user_id, level in users.items():
            uid = str(user_id)
            month_level = max(1, int(level or 1))
            await db.execute(
                """
                INSERT INTO leveling_global (user_id, global_level, updated_at)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                  global_level = global_level + %s,
                  updated_at = %s
                """,
                (uid, month_level, now, month_level, now),
            )
            updated += 1

    if updated:
        logger.info(
            "[GlobalLevel] Backfilled %s winner entries from winners.json (top 10/month only)",
            updated,
        )
    return updated
