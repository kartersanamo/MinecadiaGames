"""Unified repository for DM game session persistence (game_sessions table)."""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from core.database.pool import DatabasePool

# Canonical game_type values stored in game_sessions
GAME_TYPES = frozenset(
    {
        "wordle",
        "tictactoe",
        "connect_four",
        "memory",
        "2048",
        "minesweeper",
        "hangman",
        "filler",
        "mastermind",
        "paintball",
    }
)

# Map config / legacy table suffixes → canonical game_type
GAME_TYPE_ALIASES: Dict[str, str] = {
    "wordle": "wordle",
    "tictactoe": "tictactoe",
    "connectfour": "connect_four",
    "connect_four": "connect_four",
    "connect four": "connect_four",
    "memory": "memory",
    "2048": "2048",
    "minesweeper": "minesweeper",
    "hangman": "hangman",
    "filler": "filler",
    "mastermind": "mastermind",
    "paintball": "paintball",
    "paint ball": "paintball",
}

LEGACY_STATUS_MAP = {
    "Started": "started",
    "Won": "won",
    "Lost": "lost",
    "Tied": "tied",
    "started": "started",
    "won": "won",
    "lost": "lost",
    "tied": "tied",
}


def normalize_game_type(name: str) -> str:
    key = name.lower().replace(" ", "")
    if key in GAME_TYPE_ALIASES:
        return GAME_TYPE_ALIASES[key]
    if key.replace("_", "") in GAME_TYPE_ALIASES:
        return GAME_TYPE_ALIASES[key.replace("_", "")]
    return key


def normalize_status(status: str) -> str:
    return LEGACY_STATUS_MAP.get(status, status.lower())


class GameSessionRepository:
    def __init__(self, db: DatabasePool | None = None):
        self._db = db

    async def _pool(self) -> DatabasePool:
        return self._db or await DatabasePool.get_instance()

    async def has_session(self, game_id: int, user_id: int, game_type: str) -> bool:
        db = await self._pool()
        rows = await db.execute(
            "SELECT 1 FROM game_sessions WHERE game_id = %s AND user_id = %s AND game_type = %s LIMIT 1",
            (game_id, user_id, normalize_game_type(game_type)),
        )
        return bool(rows)

    async def start_session(
        self,
        game_id: int,
        user_id: int,
        game_type: str,
        *,
        stats: Optional[Dict[str, Any]] = None,
        state: Optional[Dict[str, Any]] = None,
        started_at: Optional[int] = None,
    ) -> None:
        db = await self._pool()
        ts = started_at or int(time.time())
        stats_json = json.dumps(stats) if stats else None
        state_json = json.dumps(state) if state else None
        await db.execute_insert(
            """INSERT INTO game_sessions
               (game_id, user_id, game_type, status, stats, state, started_at, ended_at)
               VALUES (%s, %s, %s, 'started', %s, %s, %s, NULL)""",
            (game_id, user_id, normalize_game_type(game_type), stats_json, state_json, ts),
        )

    async def update_state(
        self, game_id: int, user_id: int, game_type: str, state: Dict[str, Any]
    ) -> None:
        db = await self._pool()
        await db.execute(
            "UPDATE game_sessions SET state = %s WHERE game_id = %s AND user_id = %s AND game_type = %s",
            (json.dumps(state), game_id, user_id, normalize_game_type(game_type)),
        )

    async def merge_stats(
        self, game_id: int, user_id: int, game_type: str, stats: Dict[str, Any]
    ) -> None:
        db = await self._pool()
        await db.execute(
            """UPDATE game_sessions SET stats = JSON_MERGE_PATCH(COALESCE(stats, JSON_OBJECT()), %s)
               WHERE game_id = %s AND user_id = %s AND game_type = %s""",
            (json.dumps(stats), game_id, user_id, normalize_game_type(game_type)),
        )

    async def update_stats(
        self, game_id: int, user_id: int, game_type: str, stats: Dict[str, Any]
    ) -> None:
        db = await self._pool()
        await db.execute(
            "UPDATE game_sessions SET stats = %s WHERE game_id = %s AND user_id = %s AND game_type = %s",
            (json.dumps(stats), game_id, user_id, normalize_game_type(game_type)),
        )

    async def finish_session(
        self,
        game_id: int,
        user_id: int,
        game_type: str,
        status: str,
        *,
        stats: Optional[Dict[str, Any]] = None,
        ended_at: Optional[int] = None,
    ) -> None:
        db = await self._pool()
        ts = ended_at or int(time.time())
        norm = normalize_status(status)
        if stats is not None:
            await db.execute(
                """UPDATE game_sessions
                   SET status = %s, ended_at = %s, stats = %s
                   WHERE game_id = %s AND user_id = %s AND game_type = %s""",
                (norm, ts, json.dumps(stats), game_id, user_id, normalize_game_type(game_type)),
            )
        else:
            await db.execute(
                """UPDATE game_sessions SET status = %s, ended_at = %s
                   WHERE game_id = %s AND user_id = %s AND game_type = %s""",
                (norm, ts, game_id, user_id, normalize_game_type(game_type)),
            )

    async def abandon_started_for_user(
        self, user_id: int, game_type: str, *, ended_at: Optional[int] = None
    ) -> int:
        db = await self._pool()
        ts = ended_at or int(time.time())
        result = await db.execute(
            """UPDATE game_sessions SET status = 'lost', ended_at = %s
               WHERE user_id = %s AND game_type = %s AND status = 'started' AND game_id != -999999""",
            (ts, user_id, normalize_game_type(game_type)),
        )
        return len(result) if result else 0

    async def get_started_sessions(
        self, user_id: int, game_type: str
    ) -> List[Dict[str, Any]]:
        db = await self._pool()
        return await db.execute(
            """SELECT game_id, user_id, game_type, status, stats, state, started_at, ended_at
               FROM game_sessions
               WHERE user_id = %s AND game_type = %s AND status = 'started' AND game_id != -999999
               ORDER BY started_at DESC""",
            (user_id, normalize_game_type(game_type)),
        )

    async def get_session(
        self, game_id: int, user_id: int, game_type: str
    ) -> Optional[Dict[str, Any]]:
        db = await self._pool()
        rows = await db.execute(
            """SELECT game_id, user_id, game_type, status, stats, state, started_at, ended_at
               FROM game_sessions WHERE game_id = %s AND user_id = %s AND game_type = %s LIMIT 1""",
            (game_id, user_id, normalize_game_type(game_type)),
        )
        return rows[0] if rows else None

    async def get_active_dm_games(self) -> List[Dict[str, Any]]:
        db = await self._pool()
        return await db.execute(
            """SELECT game_id, user_id, game_type, status, started_at
               FROM game_sessions
               WHERE status = 'started' AND ended_at IS NULL AND game_id != -999999"""
        )

    async def count_wins(self, user_id: int, game_type: str) -> int:
        db = await self._pool()
        rows = await db.execute(
            """SELECT COUNT(*) AS cnt FROM game_sessions
               WHERE user_id = %s AND game_type = %s AND status = 'won'""",
            (user_id, normalize_game_type(game_type)),
        )
        return int(rows[0]["cnt"]) if rows else 0

    @staticmethod
    def parse_stats(row: Dict[str, Any]) -> Dict[str, Any]:
        raw = row.get("stats")
        if not raw:
            return {}
        if isinstance(raw, dict):
            return raw
        return json.loads(raw)

    @staticmethod
    def parse_state(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        raw = row.get("state")
        if not raw:
            return None
        if isinstance(raw, dict):
            return raw
        return json.loads(raw)


_default = GameSessionRepository()

has_session = _default.has_session
start_session = _default.start_session
update_state = _default.update_state
merge_stats = _default.merge_stats
update_stats = _default.update_stats
finish_session = _default.finish_session
abandon_started_for_user = _default.abandon_started_for_user
get_started_sessions = _default.get_started_sessions
get_session = _default.get_session
get_active_dm_games = _default.get_active_dm_games
count_wins = _default.count_wins
