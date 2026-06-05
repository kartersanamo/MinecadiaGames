import json
from typing import Any, Dict, Optional

from core.database.pool import DatabasePool
from core.logging.setup import get_logger
from repositories.game_session_repository import GameSessionRepository, normalize_game_type

logger = get_logger("GameState")


class GameStateService:
    def __init__(self, sessions: GameSessionRepository | None = None):
        self._sessions = sessions or GameSessionRepository()

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
        try:
            await self._sessions.update_state(game_id, user_id, game_type, state)
            return True
        except Exception as e:
            logger.error(
                f"Error saving game state for {game_type} game {game_id}, user {user_id}: {e}"
            )
            return False

    async def load(
        self, game_type: str, game_id: int, user_id: int
    ) -> Optional[Dict[str, Any]]:
        try:
            row = await self._sessions.get_session(game_id, user_id, game_type)
            if row:
                return GameSessionRepository.parse_state(row)
            return None
        except Exception as e:
            logger.error(
                f"Error loading game state for {game_type} game {game_id}, user {user_id}: {e}"
            )
            return None

    async def get_active_dm_games(self) -> list:
        try:
            active_games = []
            rows = await self._sessions.get_active_dm_games()
            for game in rows:
                active_games.append(
                    {
                        "game_id": game["game_id"],
                        "user_id": game["user_id"],
                        "status": game.get("status", "started"),
                        "game_type": normalize_game_type(game["game_type"]),
                    }
                )
            return active_games
        except Exception as e:
            logger.error(f"Error getting active DM games: {e}")
            return []


_default = GameStateService()
save_game_state = _default.save
load_game_state = _default.load
get_active_dm_games = _default.get_active_dm_games
