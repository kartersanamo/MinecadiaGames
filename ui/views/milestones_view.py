import discord
from core.logging.setup import get_logger
from managers.milestones import MilestonesManager
from ui.paginator import Paginator
from core.errors.decorators import safe_interaction


class MilestonesView(discord.ui.View):
    def __init__(self, bot, config, user_id: int, milestones_manager: MilestonesManager, is_own: bool = False):
        super().__init__(timeout=None)
        self.bot = bot
        self.config = config
        self.user_id = user_id
        self.milestones_manager = milestones_manager
        self.is_own = is_own
        self.logger = get_logger("UI")
        
        # Add badge selection dropdown (only if viewing own milestones)
        # We'll add this dynamically in the command since we need async access to achievements
        
        # Add game selection buttons
        milestones_config = config.get('milestones', {})
        # Filter out _comment and other non-game keys
        games = [game for game in milestones_config.keys() if not game.startswith('_')]
        
        if not games:
            # No milestones configured, buttons won't work
            return
        
        # Start buttons on row 1 to leave room for select menu on row 0
        for i, game in enumerate(games[:20]):  # Limit to 20 to leave room for select menu
            row = (i // 5) + 1  # Start from row 1
            button = discord.ui.Button(
                label=game,
                style=discord.ButtonStyle.grey,
                custom_id=f"milestones_{game}_{user_id}",
                row=row
            )
            button.callback = self.create_callback(game)
            self.add_item(button)
    
    def create_callback(self, game_type: str):
        @safe_interaction(
            self.logger,
            bot_name="Games",
            component=f"milestones_{game_type}",
        )
        async def callback(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            await self.show_game_milestones(interaction, game_type)

        return callback
    
    async def show_game_milestones(self, interaction: discord.Interaction, game_type: str):
        """Show milestones for a specific game"""
        user = self.bot.get_user(self.user_id) or await self.bot.fetch_user(self.user_id)
        milestones_config = self.config.get('milestones', {})
        game_milestones = milestones_config.get(game_type, {})
        
        if not game_milestones:
            await interaction.followup.send(f"No milestones configured for {game_type}.", ephemeral=True)
            return
        
        # Get guild for emoji resolution
        guild = interaction.guild if interaction.guild else None
        
        # Get progress for each metric
        pages = []
        for metric, milestones in game_milestones.items():
            progress = await self.milestones_manager.get_milestone_progress(self.user_id, game_type, metric)
            
            page_text = f"**{game_type} - {metric.replace('_', ' ').title()}**\n\n"
            page_text += f"Current: **{progress['current_value']}**\n\n"
            
            for milestone in progress['milestones']:
                emoji_str = milestone.get('emoji', '🏅')
                # Resolve emoji using milestones_manager
                emoji = self.milestones_manager._resolve_emoji(emoji_str, guild)
                name = milestone.get('name', 'Unknown')
                threshold = milestone.get('threshold', 0)
                current = progress['current_value']
                earned = milestone.get('earned', False)
                
                if earned:
                    page_text += f"✅ {emoji} **{name}** - {threshold}\n"
                else:
                    progress_pct = milestone.get('progress', 0)
                    page_text += f"⏳ {emoji} **{name}** - {current}/{threshold} ({progress_pct:.1f}%)\n"
            
            pages.append(page_text)
        
        if not pages:
            await interaction.followup.send(f"No milestones found for {game_type}.", ephemeral=True)
            return
        
        paginator = Paginator(bot=self.bot)
        paginator.title = f"🏆 {game_type} Milestones - {user.display_name}"
        paginator.data = pages
        paginator.sep = 1
        paginator.ephemeral = True
        
        await paginator.send(interaction)
