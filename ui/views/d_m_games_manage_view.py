import discord
from core.config.manager import ConfigManager
from managers.game_manager import GameManager
from core.logging.setup import get_logger
from services.dm_rotation_service import get_games_dict, is_vaulted, set_game_vaulted


class DMGamesManageView(discord.ui.View):
    """View for vaulting / unvaulting individual DM games from rotation."""

    def __init__(self, game_manager: GameManager, config, bot):
        super().__init__(timeout=None)
        self.game_manager = game_manager
        self.config = config
        self.bot = bot
        self.logger = get_logger("Commands")

        dm_config = config.get('dm_games')
        games_dict = get_games_dict(dm_config)

        options = []
        for game_name, game_config in games_dict.items():
            vaulted = is_vaulted(game_config)
            status = "🔒 Vaulted" if vaulted else "✅ Active"
            options.append(
                discord.SelectOption(
                    label=f"{game_name} ({status})",
                    value=game_name,
                    description=f"Toggle vault for {game_name}",
                )
            )

        if options:
            select = discord.ui.Select(
                placeholder="Select a game to vault or unvault...",
                options=options,
                custom_id="dm_games_manage_select",
                row=0,
            )
            select.callback = self.game_select_callback
            self.add_item(select)

    async def game_select_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        game_name = interaction.data.get("values", [None])[0]
        if not game_name:
            await interaction.followup.send("`❌` No game selected.", ephemeral=True)
            return

        config = getattr(self, 'config', None) or ConfigManager.get_instance()
        dm_config = config.get('dm_games')
        games_dict = get_games_dict(dm_config)

        if game_name not in games_dict:
            await interaction.followup.send(f"`❌` Game {game_name} not found.", ephemeral=True)
            return

        game_config = games_dict[game_name]
        new_vaulted = not is_vaulted(game_config)

        set_game_vaulted(config, game_name, new_vaulted)
        self.game_manager.dm_config = config.get('dm_games')

        try:
            await self.game_manager.refresh_leveling_rotation_display()
        except Exception as e:
            self.logger.warning("[DMGamesManageView] Failed to refresh leveling embed: %s", e)

        status = "vaulted" if new_vaulted else "unvaulted (active in rotation)"
        await interaction.followup.send(
            f"`✅` {game_name} has been {status}.",
            ephemeral=True,
        )

        view = DMGamesManageView(self.game_manager, config, self.bot)
        embed = discord.Embed(
            title="⚙️ Manage DM Games",
            description="Select a game to vault or unvault it from the public rotation.",
            color=discord.Color.from_str(config.get('config', 'EMBED_COLOR')),
        )
        logo_url = self.bot.app.embeds.get_logo_url(config.get('config', 'LOGO'))
        embed.set_footer(text=config.get('config', 'FOOTER'), icon_url=logo_url)
        if interaction.message:
            await interaction.message.edit(embed=embed, view=view)
