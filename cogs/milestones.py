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
from ui.views.milestones_view import MilestonesView
from ui.views.badge_select_menu_view import BadgeSelectMenu

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


async def setup(bot: commands.Bot):
    await bot.add_cog(Milestones(bot))
