from discord.ext import commands
from discord import app_commands
import discord
from core.config.manager import ConfigManager
from managers.leveling import LevelingManager
from core.logging.setup import get_logger


class AddXP(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = ConfigManager.get_instance()
        self.logger = get_logger("Commands")
    
    def _check_admin(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            return False
        
        admin_roles = self.config.get('config', 'ADMIN_ROLES', [])
        user_roles = [role.name for role in interaction.user.roles]
        
        if "*" in admin_roles:
            return True
        
        return any(role in admin_roles for role in user_roles)
    
    @app_commands.command(name="add-xp", description="Adds/Removes XP from a member")
    @app_commands.describe(member="Member to modify XP for", xp="XP amount (positive or negative)")
    async def add_xp(self, interaction: discord.Interaction, member: discord.Member, xp: str):
        if not self._check_admin(interaction):
            await interaction.response.send_message("`❌` You don't have permission to use this command.", ephemeral=True)
            return
        
        if interaction.guild is None:
            return await interaction.response.send_message(
                content="Commands cannot be run in DMs!",
                ephemeral=True
            )
        
        xp_value = self._parse_xp_input(xp)
        if xp_value is None:
            return await interaction.response.send_message(
                content="`❌` Failed! Please provide a positive or negative number.",
                ephemeral=True
            )
        
        current_xp = await self._get_current_xp(member.id)
        if current_xp is None:
            return await interaction.response.send_message(
                content="`❌` Failed! This user is not in the database. They must gain XP first!",
                ephemeral=True
            )
        
        new_xp = current_xp + xp_value
        if new_xp < 0:
            return await interaction.response.send_message(
                content="`❌` Failed! This action would result in a negative XP value!",
                ephemeral=True
            )
        
        # Get current level before update
        current_level = await self._get_current_level(member.id)
        
        # Update XP and level
        new_level = await self._update_user_xp(member.id, new_xp)
        
        # Check for milestones/achievements if level or XP changed
        if current_level != new_level or xp_value != 0:
            # Get a channel to send achievement notifications (use interaction channel or try to get a default)
            channel = interaction.channel
            if not channel or not isinstance(channel, discord.TextChannel):
                # Try to get a default channel from the guild
                guild = interaction.guild
                if guild:
                    # Try to get the leveling channel or first text channel
                    leveling_channel_id = self.config.get('config', 'LEVELING_CHANNEL')
                    if leveling_channel_id:
                        channel = guild.get_channel(leveling_channel_id)
                    if not channel:
                        # Get first text channel as fallback
                        for ch in guild.text_channels:
                            if ch.permissions_for(guild.me).send_messages:
                                channel = ch
                                break
            
            # Check level achievements if level changed
            if current_level != new_level and channel:
                from utils.achievements import check_level_achievement
                await check_level_achievement(member, new_level, channel, self.bot)
            
            # Check total XP achievements
            if channel:
                from utils.achievements import check_xp_achievement
                await check_xp_achievement(member, new_xp, channel, self.bot)
        
        # Build response message
        response = f"`✅` Successfully added `{xp_value}` XP to {member.mention}\n`XP:` `{current_xp}` → `{new_xp}`"
        if current_level != new_level:
            response += f"\n`Level:` `{current_level}` → `{new_level}`"
        
        await interaction.response.send_message(
            content=response,
            ephemeral=True
        )
    
    def _parse_xp_input(self, xp: str) -> int:
        try:
            return int(xp)
        except (ValueError, TypeError):
            return None
    
    async def _get_current_xp(self, user_id: int) -> int:
        from core.database.pool import DatabasePool
        db = await DatabasePool.get_instance()
        result = await db.execute("SELECT xp FROM leveling WHERE user_id = %s", (str(user_id),))
        if not result:
            return None
        return int(result[0]['xp'])
    
    async def _get_current_level(self, user_id: int) -> int:
        """Get current level using LevelingManager"""
        manager = LevelingManager()
        return await manager.get_user_level(user_id)
    
    async def _update_user_xp(self, user_id: int, new_xp: int) -> int:
        """Update user XP and level using LevelingManager"""
        from core.database.pool import DatabasePool
        db = await DatabasePool.get_instance()
        
        # Update XP first
        await db.execute(
            "UPDATE leveling SET xp = %s WHERE user_id = %s",
            (new_xp, str(user_id))
        )
        
        # Use LevelingManager to calculate and update level
        manager = LevelingManager()
        new_level = await manager.update_user_level(user_id, new_xp)
        
        return new_level


async def setup(bot):
    await bot.add_cog(AddXP(bot))

