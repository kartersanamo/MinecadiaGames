from typing import Any, Dict, List, Optional

from core.database.pool import DatabasePool
from repositories.game_session_repository import normalize_game_type


class GameRepository:
    def __init__(self, db: DatabasePool | None = None):
        self._db = db

    async def _pool(self) -> DatabasePool:
        return self._db or await DatabasePool.get_instance()

    async def get_last_game_id(self, game_name: str) -> Optional[int]:
        db = await self._pool()
        rows = await db.execute(
            "SELECT id AS game_id FROM games WHERE name = %s ORDER BY id DESC LIMIT 1",
            (game_name,),
        )
        return rows[0]["game_id"] if rows else None

    async def has_played_game(self, game_name: str, user_id: int, game_id: int) -> bool:
        db = await self._pool()
        game_type = normalize_game_type(game_name)
        rows = await db.execute(
            "SELECT user_id FROM game_sessions WHERE game_id = %s AND user_id = %s AND game_type = %s",
            (game_id, user_id, game_type),
        )
        return len(rows) > 0

    async def get_last_dm_game_info(self) -> Optional[Dict[str, Any]]:
        db = await self._pool()
        rows = await db.execute(
            "SELECT name AS game_name, id AS game_id FROM games WHERE is_dm = 1 ORDER BY id DESC LIMIT 1"
        )
        return rows[0] if rows else None

    async def get_recent_games(self) -> tuple[List[str], List[str]]:
        db = await self._pool()
        rows = await db.execute(
            "SELECT id AS game_id, name AS game_name, refreshed_at FROM games ORDER BY refreshed_at DESC"
        )
        game_list: List[str] = []
        game_str: List[str] = []
        for row in rows:
            game_str.append(
                f"`#{row['game_id']}` **{row['game_name'].title()}** <t:{row['refreshed_at']}:R>"
            )
            game_list.append(f"{row['game_id']} {row['game_name'].title()}")
        return game_str, game_list
