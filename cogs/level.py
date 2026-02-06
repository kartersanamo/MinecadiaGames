from discord.ext import commands
from discord import app_commands
import discord
from core.config.manager import ConfigManager
from core.database.pool import DatabasePool
from core.logging.setup import get_logger
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from pathlib import Path
import requests
import os
import uuid


class Level(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = ConfigManager.get_instance()
        self.logger = get_logger("Commands")
        self.GAMES_CHANNEL_ID = 1456658225964388504  # #games channel
    
    @app_commands.command(name="level", description="View your level and XP")
    @app_commands.describe(user="The user to view the level of (leave empty to view your own)")
    async def level(self, interaction: discord.Interaction, user: discord.Member = None):
        if interaction.guild is None:
            await interaction.response.send_message(
                content="Commands cannot be ran in DMs!",
                ephemeral=False
            )
            return
        
        # Check if in #games channel
        if interaction.channel.id != self.GAMES_CHANNEL_ID:
            await interaction.response.send_message(
                f"`❌` This command can only be used in <#{self.GAMES_CHANNEL_ID}>.",
                ephemeral=False
            )
            return
        
        # Use provided user or default to command user
        target_user = user if user else interaction.user
        
        # Send initial response
        if user:
            await interaction.response.send_message(content=f"Fetching {target_user.display_name}'s level card...", ephemeral=False)
        else:
            await interaction.response.send_message(content="Sending your level card...", ephemeral=False)
        
        import asyncio
        db = await asyncio.wait_for(DatabasePool.get_instance(), timeout=5.0)
        rows = await asyncio.wait_for(
            db.execute(
                "SELECT * FROM leveling WHERE user_id = %s",
                (str(target_user.id),)
            ),
            timeout=5.0
        )
        
        if not rows:
            if user:
                await interaction.edit_original_response(
                    content=f"{target_user.display_name} hasn't earned any XP yet!"
                )
            else:
                await interaction.edit_original_response(
                    content="You haven't earned any XP yet! Start chatting and playing games to level up!"
                )
            return
        
        stats = rows[0]
        level = int(stats.get('level', 0))
        xp = int(stats.get('xp', 0))
        
        # Get level data
        level_data = self.config.get('levels')
        # Support both old (LEVELS) and new (levels) structure
        levels_dict = level_data.get('LEVELS', {}) or level_data.get('levels', {})
        next_level = level + 1
        required_xp = levels_dict.get(str(next_level), 0)
        
        if not required_xp:
            # If no next level, use current XP as required
            required_xp = xp
        
        # Get user badges for display
        from managers.milestones import MilestonesManager
        milestones_manager = MilestonesManager()
        badges = await milestones_manager.get_user_badges(target_user.id)
        
        # Generate the level card image
        output_path = None
        try:
            file, output_path = await self._generate_level_card(target_user, level, xp, required_xp, badges, interaction.guild)
            
            # Get daily streak
            from cogs.daily import Daily
            daily_streak = await Daily.get_daily_streak(target_user.id)
            streak_text = f" | 🔥 {daily_streak['streak']} day streak" if daily_streak['streak'] > 0 else ""
            
            # Add text content showing level and XP in case image doesn't load
            content_text = f"**Level {level}** | **{xp:,} XP** / **{required_xp:,} XP**{streak_text}"
            
            await interaction.edit_original_response(content=content_text, attachments=[file])
        except Exception as e:
            self.logger.error(f"Error generating level card: {e}", exc_info=True)
            if user:
                await interaction.edit_original_response(
                    content=f"An error occurred while generating {target_user.display_name}'s level card. Please try again later."
                )
            else:
                await interaction.edit_original_response(
                    content="An error occurred while generating your level card. Please try again later."
                )
        finally:
            # Always clean up temp file after sending (or if error occurred)
            if output_path:
                try:
                    if os.path.exists(output_path):
                        os.remove(output_path)
                        self.logger.debug(f"Deleted level card file: {output_path}")
                except Exception as cleanup_error:
                    self.logger.warning(f"Failed to delete level card file {output_path}: {cleanup_error}")
    
    async def _generate_level_card(self, user: discord.Member, level: int, xp: int, required_xp: int, badges: list = None, guild: discord.Guild = None) -> tuple[discord.File, str]:
        """Generate a level card image with user avatar, level, and XP.
        
        Args:
            user: The user to generate the card for
            level: User's current level
            xp: User's current XP
            required_xp: XP required for next level
            badges: List of badge dictionaries with emoji info
            guild: Discord guild to look up emoji objects
        
        Returns:
            tuple: (discord.File, output_path) - The file object and path for cleanup
        """
        from pathlib import Path
        
        # Get paths
        assets_path = Path(__file__).parent.parent / "assets"
        base_image_path = assets_path / "Images" / "RankCard.png"
        font_path = assets_path / "Fonts" / "BarlowCondensed-Black.ttf"
        default_avatar_path = assets_path / "Images" / "Default.png"
        
        # Create output filename
        output_filename = f"level_{uuid.uuid4()}.png"
        output_path = output_filename
        
        with Image.open(base_image_path) as base_image:
            # Create circular mask for avatar
            mask = Image.new("L", (343, 343), 0)
            draw_mask = ImageDraw.Draw(mask)
            draw_mask.ellipse((0, 0, 343, 343), fill=255, outline="#060e1a", width=12)
            
            # Get user avatar
            if user.avatar:
                try:
                    response = requests.get(user.avatar.url)
                    if "gif" in user.avatar.url:
                        # Handle GIF avatars
                        with Image.open(BytesIO(response.content)) as im:
                            im.seek(0)
                            temp_path = f"temp_avatar_{uuid.uuid4()}.png"
                            im.save(temp_path)
                        profile_picture = Image.open(temp_path)
                        # Clean up temp file after use
                        try:
                            os.remove(temp_path)
                        except:
                            pass
                    else:
                        profile_picture = Image.open(BytesIO(response.content))
                except Exception as e:
                    self.logger.error(f"Error loading avatar: {e}")
                    profile_picture = Image.open(default_avatar_path)
            else:
                profile_picture = Image.open(default_avatar_path)
            
            # Process avatar
            profile_picture = profile_picture.convert("RGBA")
            profile_picture = profile_picture.resize(size=(343, 343))
            profile_picture.putalpha(mask)
            
            # Paste avatar onto base image
            base_image.paste(profile_picture, (40, 47), profile_picture)
            
            # Draw text
            draw = ImageDraw.Draw(base_image)
            font = ImageFont.truetype(str(font_path), 68)
            
            # Draw XP/Required XP at (542, 197) - scale to fit
            xp_text = f"{xp}/{required_xp}"
            xp_max_width = 200  # Maximum width for XP text area
            xp_font_size = 68
            xp_font = ImageFont.truetype(str(font_path), xp_font_size)
            xp_bbox = draw.textbbox((0, 0), xp_text, font=xp_font)
            xp_width = xp_bbox[2] - xp_bbox[0]
            
            # Scale down font if text is too wide
            if xp_width > xp_max_width:
                xp_font_size = int(xp_font_size * (xp_max_width / xp_width))
                xp_font = ImageFont.truetype(str(font_path), xp_font_size)
            
            draw.text(
                (542, 197),
                xp_text,
                font=xp_font,
                fill="white",
                stroke_width=2,
                stroke_fill="black"
            )
            
            # Draw Level at (645, 269) - scale to fit
            level_text = f"{level}"
            level_max_width = 100  # Maximum width for level text area
            level_font_size = 68
            level_font = ImageFont.truetype(str(font_path), level_font_size)
            level_bbox = draw.textbbox((0, 0), level_text, font=level_font)
            level_width = level_bbox[2] - level_bbox[0]
            
            # Scale down font if text is too wide
            if level_width > level_max_width:
                level_font_size = int(level_font_size * (level_max_width / level_width))
                level_font = ImageFont.truetype(str(font_path), level_font_size)
            
            draw.text(
                (645, 269),
                level_text,
                font=level_font,
                fill="white",
                stroke_width=2,
                stroke_fill="black"
            )
            
            # Draw username at (440, 430) - scale to fit
            username_text = f"@{user.name}"
            
            # Add badge emoji images if available (display top 3 badges)
            badge_x_offset = 440  # Start position for badges
            badge_size = 48  # Smaller badge size
            badge_spacing = 5  # Closer spacing between badges
            badge_y = 380  # Move badges up to go over yellow line
            
            if badges and guild:
                for i, badge in enumerate(badges[:3]):
                    emoji_str = badge.get('emoji', '')
                    if not emoji_str:
                        continue
                    
                    # Resolve emoji name to actual emoji object
                    emoji_name = emoji_str.strip(':')
                    emoji = discord.utils.get(guild.emojis, name=emoji_name)
                    
                    if emoji:
                        try:
                            # Download emoji image
                            emoji_url = emoji.url
                            response = requests.get(emoji_url)
                            if response.status_code == 200:
                                # Open emoji image
                                emoji_img = Image.open(BytesIO(response.content))
                                emoji_img = emoji_img.convert("RGBA")
                                
                                # Resize emoji to badge size
                                emoji_img = emoji_img.resize((badge_size, badge_size), Image.Resampling.LANCZOS)
                                
                                # Calculate position (badges positioned above yellow line)
                                badge_x = badge_x_offset + (i * (badge_size + badge_spacing))
                                
                                # Paste emoji onto base image
                                base_image.paste(emoji_img, (badge_x, badge_y), emoji_img)
                        except Exception as e:
                            self.logger.error(f"Error loading badge emoji {emoji_name}: {e}")
            
            # Calculate username position and scale to fit
            username_x = 440
            username_y = 430
            username_max_width = 400  # Maximum width for username (from 440 to ~840, leaving some margin)
            
            # Adjust username position if badges are present
            if badges and guild and any(badge.get('emoji') for badge in badges[:3]):
                num_badges = min(3, len([b for b in badges[:3] if b.get('emoji')]))
                username_x = 440 + (num_badges * (badge_size + badge_spacing)) + 10
                # Recalculate max width based on new position
                username_max_width = base_image.width - username_x - 20  # Leave 20px margin from right edge
            
            # Scale username font to fit
            username_font_size = 68
            username_font = ImageFont.truetype(str(font_path), username_font_size)
            username_bbox = draw.textbbox((0, 0), username_text, font=username_font)
            username_width = username_bbox[2] - username_bbox[0]
            
            # Scale down font if text is too wide
            if username_width > username_max_width:
                username_font_size = int(username_font_size * (username_max_width / username_width))
                username_font = ImageFont.truetype(str(font_path), username_font_size)
            
            draw.text(
                (username_x, username_y),
                username_text,
                font=username_font,
                fill="white",
                stroke_width=2,
                stroke_fill="black"
            )
            
            # Save image
            base_image.save(output_path)
        
        # Return as Discord file and path for cleanup
        return discord.File(output_path, filename="Level.png"), output_path


async def setup(bot):
    await bot.add_cog(Level(bot))

