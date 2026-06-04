from services.asset_path_service import AssetPathService
from datetime import datetime, timezone
import discord
from games.base.dm_game import DMGame
from core.logging.setup import get_logger
class ConnectFour(DMGame):
    def __init__(self, bot):
        super().__init__(bot)
        # Support both old and new config structure
        games = self.dm_config.get('GAMES', {})
        if not games:
            games = self.dm_config.get('games', {})
        self.game_config = games.get('Connect Four', {})
        self.logger = get_logger("DMGames")
    
    async def _run_game(self, user: discord.User, game_name: str, test_mode: bool = False) -> bool:
        try:
            last_game_id = await self.bot.app.games.get_last_game_id('connect four')
            if not last_game_id:
                return False
            
            embed = discord.Embed(
                title=f"Connect Four #{last_game_id}",
                description="Welcome to Connect Four! Begin by choosing a position below!",
                color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR'))
            )
            embed.add_field(name="Number of Moves", value="0")
            logo_url = self.bot.app.embeds.get_logo_url(self.config.get('config', 'LOGO'))
            embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
            
            # Calculate project root: games/dm/connect_four.py -> games/dm/ -> games/ -> project_root/
            project_root = AssetPathService.PROJECT_ROOT
            # Support both old and new structure
            assets = self.game_config.get('assets', {})
            base_image_path = self.game_config.get("base_image_path") or assets.get("board", "assets/Images/ConnectFourBoard.png")
            base_path = project_root / base_image_path
            file = discord.File(str(base_path), filename="ConnectFourBoard.png")
            embed.set_image(url="attachment://ConnectFourBoard.png")
            
            from games.dm.connect_four.connect_four_buttons import ConnectFourButtons
            view = ConnectFourButtons(last_game_id, self.bot, self.config, self.game_config, test_mode=test_mode)
            view.player_id = user.id  # Store player_id for state saving
            # Register view for persistence across bot restarts
            self.bot.add_view(view)
            await user.send(file=file, embed=embed, view=view)
            
            # Save initial state
            if not test_mode:
                await view._save_state()
            
            db = await self._get_db()
            current_unix = int(datetime.now(timezone.utc).timestamp())
            await db.execute_insert(
                "INSERT INTO users_connectfour (game_id, user_id, status, moves, ended_at, started_at) VALUES (%s, %s, %s, %s, %s, %s)",
                (last_game_id, user.id, 'Started', 0, 0, current_unix)
            )
            
            self.logger.info(f"Connect Four ({user.name}#{user.discriminator})")
            return True
        except Exception as e:
            self.logger.error(f"Connect Four error: {e}")
            return False
