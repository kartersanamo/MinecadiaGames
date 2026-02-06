from discord.ext import commands
from discord import app_commands
import discord
from core.database.pool import DatabasePool
from core.logging.setup import get_logger
from core.config.manager import ConfigManager
from managers.milestones import MilestonesManager
from datetime import datetime, timezone
from typing import Optional
from utils.paginator import Paginator


class Milestones(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = ConfigManager.get_instance()
        self.logger = get_logger("Commands")
        self.milestones_manager = MilestonesManager()
        self.GAMES_CHANNEL_ID = 1456658225964388504  # #games channel
    
    @app_commands.command(name="milestones", description="View your milestones and achievements")
    @app_commands.describe(user="View another user's milestones (optional)")
    async def milestones(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        if interaction.guild is None:
            await interaction.response.send_message("`❌` This command can only be used in a server.", ephemeral=False)
            return
        
        # Check if in #games channel
        if interaction.channel.id != self.GAMES_CHANNEL_ID:
            await interaction.response.send_message(
                f"`❌` This command can only be used in <#{self.GAMES_CHANNEL_ID}>.",
                ephemeral=False
            )
            return
        
        # Ensure target_user is a Member object
        if user:
            target_user = user
        else:
            # If no user specified, use the interaction user
            # Make sure it's a Member (should be if in guild)
            if isinstance(interaction.user, discord.Member):
                target_user = interaction.user
            else:
                # Fallback: try to get member from guild
                if interaction.guild:
                    target_user = interaction.guild.get_member(interaction.user.id) or interaction.user
                else:
                    target_user = interaction.user
        
        await interaction.response.defer(ephemeral=False)
        
        try:
            # Get all milestones config
            milestones_config = self.config.get('milestones', {})
            
            # Create view with game selection
            view = MilestonesView(self.bot, self.config, target_user.id, self.milestones_manager, target_user.id == interaction.user.id)
            
            # Add badge selection dropdown if viewing own milestones
            achievements = None
            if target_user.id == interaction.user.id:
                try:
                    achievements = await self.milestones_manager.get_user_achievements(target_user.id)
                    if achievements:
                        # Get currently selected badge
                        selected_badge_id = None
                        try:
                            selected_badge_id = await self.milestones_manager.get_selected_badge(target_user.id)
                        except Exception as e:
                            self.logger.warning(f"Error getting selected badge for {target_user.id}: {e}")
                            pass
                        
                        badge_select = BadgeSelectMenu(self.bot, self.milestones_manager, target_user, achievements, selected_badge_id)
                        view.add_item(badge_select)
                except Exception as e:
                    self.logger.error(f"Error getting achievements for {target_user.id}: {e}")
                    import traceback
                    self.logger.error(traceback.format_exc())
                    # Continue without badge select menu
            
            embed = await self._create_overview_embed(target_user)
            
            await interaction.followup.send(embed=embed, view=view, ephemeral=False)
        except Exception as e:
            self.logger.error(f"Error in milestones command for user {target_user.id}: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            try:
                await interaction.followup.send(f"`❌` An error occurred while loading milestones: {str(e)}", ephemeral=False)
            except:
                pass
    
    async def _create_overview_embed(self, user: discord.Member) -> discord.Embed:
        """Create overview embed showing total achievements"""
        try:
            achievements = await self.milestones_manager.get_user_achievements(user.id)
        except Exception as e:
            self.logger.error(f"Error getting achievements for {user.id} in _create_overview_embed: {e}")
            achievements = []
        
        try:
            badges = await self.milestones_manager.get_user_badges(user.id)
        except Exception as e:
            self.logger.error(f"Error getting badges for {user.id} in _create_overview_embed: {e}")
            badges = []
        
        # Get guild for emoji resolution
        guild = user.guild if hasattr(user, 'guild') and user.guild else None
        
        embed = discord.Embed(
            title=f"🏆 Milestones & Achievements - {user.display_name}",
            color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR')),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(
            name="📊 Overview",
            value=(
                f"**Total Achievements:** {len(achievements)}\n"
                f"**Active Badges:** {len(badges)}"
            ),
            inline=False
        )
        
        # Show all earned badges as emojis
        if achievements:
            badge_emojis_list = []
            for achievement in achievements:
                emoji_str = achievement.get('emoji', '🏅')
                # Resolve emoji using milestones_manager
                resolved_emoji = self.milestones_manager._resolve_emoji(emoji_str, guild)
                badge_emojis_list.append(resolved_emoji)
            badge_emojis = " ".join(badge_emojis_list)
            embed.add_field(
                name="🏅 Your Badges",
                value=badge_emojis if badge_emojis else "No badges earned yet.",
                inline=False
            )
        
        # Show recent achievements
        if achievements:
            recent = achievements[:5]
            recent_lines = []
            for achievement in recent:
                emoji_str = achievement.get('emoji', '🏅')
                # Resolve emoji using milestones_manager
                resolved_emoji = self.milestones_manager._resolve_emoji(emoji_str, guild)
                name = achievement.get('name', 'Unknown')
                recent_lines.append(f"{resolved_emoji} **{name}**")
            recent_text = "\n".join(recent_lines)
            embed.add_field(
                name="🎯 Recent Achievements",
                value=recent_text,
                inline=False
            )
        
        embed.set_thumbnail(url=user.display_avatar.url)
        from utils.helpers import get_embed_logo_url
        logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
        embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
        
        return embed


class MilestonesView(discord.ui.View):
    def __init__(self, bot, config, user_id: int, milestones_manager: MilestonesManager, is_own: bool = False):
        super().__init__(timeout=None)
        self.bot = bot
        self.config = config
        self.user_id = user_id
        self.milestones_manager = milestones_manager
        self.is_own = is_own
        
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
        async def callback(interaction: discord.Interaction):
            try:
                await interaction.response.defer(ephemeral=True)
                await self.show_game_milestones(interaction, game_type)
            except Exception as e:
                self.logger.error(f"Error in milestones button callback for {game_type}: {e}")
                import traceback
                self.logger.error(traceback.format_exc())
                try:
                    if interaction.response.is_done():
                        await interaction.followup.send(f"`❌` An error occurred: {str(e)}", ephemeral=True)
                    else:
                        await interaction.response.send_message(f"`❌` An error occurred: {str(e)}", ephemeral=True)
                except:
                    pass
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
        
        paginator = Paginator()
        paginator.title = f"🏆 {game_type} Milestones - {user.display_name}"
        paginator.data = pages
        paginator.sep = 1
        paginator.ephemeral = True
        
        await paginator.send(interaction)


class BadgeSelectMenu(discord.ui.Select):
    def __init__(self, bot, milestones_manager: MilestonesManager, user: discord.Member, achievements: list, selected_badge_id: Optional[str] = None):
        self.bot = bot
        self.milestones_manager = milestones_manager
        self.user = user
        self.achievements = achievements  # Store for use in callback
        
        # Create options from achievements
        options = [
            discord.SelectOption(
                label="None (Use Highest Priority)",
                value="none",
                description="Remove custom badge selection",
                emoji="❌",
                default=(selected_badge_id is None)
            )
        ]
        
        # Add all earned achievements as options
        for achievement in achievements:
            achievement_id = achievement.get('id', '')
            name = achievement.get('name', 'Unknown')
            emoji_str = achievement.get('emoji', '🏅')
            
            # Truncate name if too long (Discord limit is 100 chars for label)
            label = name[:95] if len(name) <= 100 else name[:92] + "..."
            
            # Resolve emoji to proper format for SelectOption
            emoji_obj = self._parse_emoji_for_select(emoji_str, user.guild if user.guild else None)
            
            options.append(
                discord.SelectOption(
                    label=label,
                    value=achievement_id,
                    description=f"{achievement.get('description', '')[:100]}",
                    emoji=emoji_obj,
                    default=(achievement_id == selected_badge_id)
                )
            )
        
        super().__init__(
            placeholder="Select badge to display...",
            options=options[:25],  # Discord limit is 25 options
            row=0
        )
    
    def _parse_emoji_for_select(self, emoji_str: str, guild: Optional[discord.Guild] = None):
        """Parse emoji string to discord.PartialEmoji or Unicode emoji for SelectOption"""
        if not emoji_str:
            return None
        
        # If it's already a Unicode emoji (single character or common emoji), use it directly
        # Check if it's a standard Unicode emoji (not starting with : or <)
        if not emoji_str.startswith(':') and not emoji_str.startswith('<'):
            return emoji_str
        
        # Resolve custom emoji using milestones_manager
        resolved = self.milestones_manager._resolve_emoji(emoji_str, guild)
        
        # If resolved to <:name:id> format, parse it to PartialEmoji
        if resolved.startswith('<') and resolved.endswith('>'):
            # Format: <:name:id> or <a:name:id> for animated
            is_animated = resolved.startswith('<a:')
            # Remove < and >
            inner = resolved[1:-1]
            # Remove a: if animated
            if is_animated:
                inner = inner[2:]
            else:
                inner = inner[1:]  # Remove :
            
            # Split by : to get name and id
            parts = inner.split(':')
            if len(parts) == 2:
                emoji_name, emoji_id = parts
                try:
                    return discord.PartialEmoji(name=emoji_name, id=int(emoji_id), animated=is_animated)
                except (ValueError, TypeError):
                    # If parsing fails, return None (no emoji)
                    return None
        
        # If it's still in :name: format and not found, try to use it as Unicode
        # But Discord won't accept :name: format, so return None
        if emoji_str.startswith(':') and emoji_str.endswith(':'):
            return None
        
        # Fallback: return as-is if it's a valid Unicode emoji
        return emoji_str if len(emoji_str) <= 2 else None
    
    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("This is not your milestones page!", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        selected_value = self.values[0]
        
        try:
            if selected_value == "none":
                await self.milestones_manager.set_selected_badge(self.user.id, None)
                badge_emoji = None
            else:
                await self.milestones_manager.set_selected_badge(self.user.id, selected_value)
                milestone = self.milestones_manager._find_milestone_by_id(selected_value)
                emoji_str = milestone.get('emoji') if milestone else None
                badge_emoji = self.milestones_manager._resolve_emoji(emoji_str, interaction.guild) if emoji_str else None
            
            # Update the select menu default
            for option in self.options:
                option.default = (option.value == selected_value)
            
            # Send confirmation
            if badge_emoji:
                await interaction.followup.send(
                    f"✅ Badge updated! Your display badge is now {badge_emoji}. This badge will appear on your level card and leaderboards.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "✅ Badge selection removed! Using highest priority badge for display.",
                    ephemeral=True
                )
            
            # Update the message to reflect the change
            try:
                await interaction.edit_original_response(view=self.view)
            except:
                pass
                
        except Exception as e:
            self.milestones_manager.logger.error(f"Error in badge selection: {e}")
            import traceback
            self.milestones_manager.logger.error(traceback.format_exc())
            await interaction.followup.send(
                f"❌ An error occurred while updating your badge: {str(e)}",
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Milestones(bot))

