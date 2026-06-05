import json
from typing import Any, Dict, Optional

from core.database.pool import DatabasePool
from core.logging.setup import get_logger

logger = get_logger("GameState")


class GameStateService:
    TABLE_MAP = {
        "2048": "users_2048",
        "tictactoe": "users_tictactoe",
        "connectfour": "users_connectfour",
        "memory": "users_memory",
        "minesweeper": "users_minesweeper",
        "hangman": "users_hangman",
        "filler": "users_filler",
    }

    ACTIVE_DM_TABLES = [
        ("2048", "users_2048", "status"),
        ("tictactoe", "users_tictactoe", "won"),
        ("connectfour", "users_connectfour", "status"),
        ("memory", "users_memory", "won"),
        ("minesweeper", "users_minesweeper", "won"),
        ("hangman", "users_hangman", "won"),
        ("filler", "users_filler", "won"),
    ]

    @classmethod
    def _table_name(cls, game_type: str) -> Optional[str]:
        return cls.TABLE_MAP.get(game_type.lower())

    async def save(
        self,
        game_type: str,
        game_id: int,
        user_id: int,
        state: Dict[str, Any],
        test_mode: bool = False,
    ) -> bool:
        if test_mode or game_id == -999999:
            return False
        table_name = self._table_name(game_type)
        if not table_name:
            logger.error(f"Unknown game type: {game_type}")
            return False
        try:
            db = await DatabasePool.get_instance()
            state_json = json.dumps(state)
            await db.execute(
                f"UPDATE {table_name} SET game_state = %s WHERE game_id = %s AND user_id = %s",
                (state_json, game_id, user_id),
            )
            return True
        except Exception as e:
            logger.error(
                f"Error saving game state for {game_type} game {game_id}, user {user_id}: {e}"
            )
            return False

    async def load(
        self, game_type: str, game_id: int, user_id: int
    ) -> Optional[Dict[str, Any]]:
        table_name = self._table_name(game_type)
        if not table_name:
            logger.error(f"Unknown game type: {game_type}")
            return None
        try:
            db = await DatabasePool.get_instance()
            result = await db.execute(
                f"SELECT game_state FROM {table_name} WHERE game_id = %s AND user_id = %s",
                (game_id, user_id),
            )
            if result and len(result) > 0:
                state_json = result[0].get("game_state")
                if state_json:
                    return json.loads(state_json)
            return None
        except Exception as e:
            logger.error(
                f"Error loading game state for {game_type} game {game_id}, user {user_id}: {e}"
            )
            return None

    async def get_active_dm_games(self) -> list:
        try:
            db = await DatabasePool.get_instance()
            active_games = []
            for game_type, table_name, status_column in self.ACTIVE_DM_TABLES:
                try:
                    query = (
                        f"SELECT game_id, user_id, {status_column} as status FROM {table_name} "
                        f"WHERE {status_column} = 'Started' AND ended_at = 0"
                    )
                    games = await db.execute(query)
                    for game in games:
                        game["game_type"] = game_type
                        active_games.append(game)
                except Exception as e:
                    logger.error(f"Error querying active {game_type} games: {e}")
            return active_games
        except Exception as e:
            logger.error(f"Error getting active DM games: {e}")
            return []


_default = GameStateService()
save_game_state = _default.save
load_game_state = _default.load
get_active_dm_games = _default.get_active_dm_games
