from typing import Any, Dict, List, Optional

from core.database.pool import DatabasePool


class GameRepository:
    def __init__(self, db: DatabasePool | None = None):
        self._db = db

    async def _pool(self) -> DatabasePool:
        return self._db or await DatabasePool.get_instance()

    async def get_last_game_id(self, game_name: str) -> Optional[int]:
        db = await self._pool()
        rows = await db.execute(
            "SELECT game_id FROM games WHERE game_name = %s ORDER BY game_id DESC LIMIT 1",
            (game_name,),
        )
        return rows[0]["game_id"] if rows else None

    async def has_played_game(self, game_name: str, user_id: int, game_id: int) -> bool:
        db = await self._pool()
        safe_game_name = game_name.lower().replace(" ", "")
        rows = await db.execute(
            f"SELECT user_id FROM users_{safe_game_name} WHERE game_id = %s AND user_id = %s",
            (game_id, user_id),
        )
        return len(rows) > 0

    async def get_last_dm_game_info(self) -> Optional[Dict[str, Any]]:
        db = await self._pool()
        rows = await db.execute(
            "SELECT game_name, game_id FROM games WHERE dm_game = TRUE ORDER BY game_id DESC LIMIT 1"
        )
        return rows[0] if rows else None

    async def get_recent_games(self) -> tuple[List[str], List[str]]:
        db = await self._pool()
        rows = await db.execute("SELECT * FROM games ORDER BY refreshed_at DESC")
        game_list: List[str] = []
        game_str: List[str] = []
        for row in rows:
            game_str.append(
                f"`#{row['game_id']}` **{row['game_name'].title()}** <t:{row['refreshed_at']}:R>"
            )
            game_list.append(f"{row['game_id']} {row['game_name'].title()}")
        return game_str, game_list
