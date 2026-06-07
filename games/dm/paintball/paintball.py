from datetime import datetime, timezone

import discord

from core.logging.setup import get_logger
from games.base.dm_game import DMGame
from games.dm.paintball.paintball_buttons import PaintballButtons
from repositories.game_session_repository import GameSessionRepository


class Paintball(DMGame):
    def __init__(self, bot):
        super().__init__(bot)
        games = self.dm_config.get("GAMES", {})
        if not games:
            games = self.dm_config.get("games", {})
        self.game_config = games.get("Paintball", {})
        self.logger = get_logger("DMGames")

    async def _run_game(self, user: discord.User, game_name: str, test_mode: bool = False) -> bool:
        try:
            if test_mode:
                last_game_id = -999999
            else:
                last_game_id = await self.bot.app.games.get_last_game_id("paintball")
                if not last_game_id:
                    return False

            view = PaintballButtons(
                last_game_id, self.bot, self.config, self.game_config, test_mode=test_mode
            )
            view.player_id = user.id
            self.bot.add_view(view)

            embed = view.build_embed()
            message = await user.send(embed=embed, view=view)
            view.message = message

            if not test_mode:
                await view._save_state()
                current_unix = int(datetime.now(timezone.utc).timestamp())
                await GameSessionRepository().start_session(
                    last_game_id,
                    user.id,
                    "paintball",
                    stats={
                        "rounds": 0,
                        "player_lives": view.state.player_lives,
                        "bot_lives": view.state.bot_lives,
                    },
                    started_at=current_unix,
                )

            self.logger.info(f"Paintball ({user.name}#{user.discriminator})")
            return True
        except Exception as e:
            self.logger.error(f"Paintball error: {e}")
            return False
