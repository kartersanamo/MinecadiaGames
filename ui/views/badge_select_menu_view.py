import discord
from managers.milestones import MilestonesManager
from typing import Optional


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
            except Exception:
                pass
                
        except Exception as e:
            self.milestones_manager.logger.error(f"Error in badge selection: {e}")
            import traceback
            self.milestones_manager.logger.error(traceback.format_exc())
            await interaction.followup.send(
                f"❌ An error occurred while updating your badge: {str(e)}",
                ephemeral=True
            )
