from discord.ext import commands, tasks
from discord import app_commands
from typing import Literal
from datetime import datetime, timezone
import asyncio
import discord
from core.config.manager import ConfigManager
from core.database.pool import DatabasePool
from ui.dm_games_view import DMGamesView
from ui.sendgames_view import SendGamesView, ViewMore
from core.logging.setup import get_logger


class SendGames(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = ConfigManager.get_instance()
        self.logger = get_logger("Tasks")
    
    @commands.Cog.listener()
    async def on_ready(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self.update_leaderboard.start()
    
    @tasks.loop(minutes=10)
    async def update_leaderboard(self):
        try:
            guild = self.bot.get_guild(self.config.get('config', 'GUILD_ID'))
            if not guild:
                return
            
            channel = guild.get_channel(1186036927514812426)
            if not channel:
                return
            
            # Get active game info for the leaderboard embed
            info_last_game = await self.get_active_game()
            if info_last_game and isinstance(info_last_game, dict):
                active = info_last_game.get('game_name') or info_last_game.get('game_name', 'Unknown')
                refreshed_at = info_last_game.get('refreshed_at')
                if refreshed_at:
                    last = int(refreshed_at)
                    new_dm_game = last + 7200
                else:
                    new_dm_game = 0
                game_sequence = ["TicTacToe", "Wordle", "Connect Four", "Memory", "2048", "Minesweeper", "Hangman"]
                rotation_display = " → ".join(
                    f"**{g}**" if g.lower().replace(" ", "") == active.lower().replace(" ", "") else g
                    for g in game_sequence
                )
                
                embed = discord.Embed(
                    color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR')),
                    title="Leaderboard <:minecadia_2:1444800686372950117>",
                    description=(
                        await SendGamesView.get_leaderboard(guild, self.bot) +
                        '\n\n'
                        f'✅ **Active DM Game**: {active}\n'
                        f'🚨 **Next DM Game**: <t:{new_dm_game}:R>\n'
                        f"-# {rotation_display}"
                    )
                )
            else:
                embed = discord.Embed(
                    color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR')),
                    title="Leaderboard <:minecadia_2:1444800686372950117>",
                    description=await SendGamesView.get_leaderboard(guild, self.bot)
                )
            
            # Only set thumbnail if logo is a valid URL (not a local file path)
            from utils.helpers import get_embed_logo_url
            logo_url = get_embed_logo_url("Assets/Logo.png")
            if logo_url:
                embed.set_thumbnail(url=logo_url)
            embed.set_image(url="https://i.imgur.com/z3bbBSA.png")
            
            # Find and update the leaderboard message (second message)
            async for message in channel.history(limit=10):
                if message.embeds and len(message.embeds) > 0:
                    if "Leaderboard" in message.embeds[0].title:
                        # Update with DMGamesView if we have active game info
                        if info_last_game and isinstance(info_last_game, dict) and 'game_name' in info_last_game:
                            try:
                                active_game_name = str(info_last_game.get('game_name', '')).lower()
                                view = DMGamesView(self.bot, active_game_name)
                                await message.edit(embed=embed, view=view)
                            except Exception as view_error:
                                self.logger.error(f"Error creating DMGamesView: {view_error}")
                                await message.edit(embed=embed)
                        else:
                            await message.edit(embed=embed)
                        break
        except Exception as e:
            self.logger.error(f"Leaderboard update error: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
    
    async def get_active_game(self):
        try:
            db = await asyncio.wait_for(DatabasePool.get_instance(), timeout=5.0)
            rows = await asyncio.wait_for(
                db.execute(
                    "SELECT game_name, refreshed_at FROM games WHERE dm_game = TRUE ORDER BY refreshed_at DESC LIMIT 1"
                ),
                timeout=5.0
            )
            if rows and len(rows) > 0:
                result = rows[0]
                # Ensure result is a dict, not a string
                if isinstance(result, dict):
                    return result
                elif isinstance(result, (list, tuple)) and len(result) >= 2:
                    # Handle tuple/list result
                    return {'game_name': result[0], 'refreshed_at': result[1]}
                else:
                    self.logger.warning(f"Unexpected result type from get_active_game: {type(result)}")
                    return None
            return None
        except Exception as e:
            self.logger.error(f"Error in get_active_game: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            return None
    
    @app_commands.command(name="send-games", description="Sends a message prompt.")
    @app_commands.describe(option="The message that you'd wish to send")
    async def sendgames(self, interaction: discord.Interaction, option: Literal["Leveling"]):
        if interaction.guild is None:
            return await interaction.response.send_message(
                content="Commands cannot be ran in DMs!",
                ephemeral=True
            )
        
        await interaction.response.send_message(content="Sending your message...", ephemeral=True)
        
        info_last_game = await self.get_active_game()
        if not info_last_game:
            await interaction.followup.send("`❌` No active DM game found.", ephemeral=True)
            return
        
        active = info_last_game['game_name']
        last = int(info_last_game['refreshed_at'])
        new_dm_game = last + 7200
        game_sequence = ["TicTacToe", "Wordle", "Connect Four", "Memory", "2048", "Minesweeper", "Hangman"]
        rotation_display = " → ".join(
            f"**{g}**" if g.lower().replace(" ", "") == active.lower().replace(" ", "") else g
            for g in game_sequence
        )
        
        if option == "Leveling":
            embed1 = discord.Embed(
                color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR')),
                title="Leveling System <:minecadia_2:1444800686372950117>",
                description=(
                    'Welcome to the **Minecadia Leveling System**! 🎮\n\n'
                    'Your level reflects your activity and engagement in our Discord server. Earn XP by chatting, reacting to messages, playing games, and participating in various activities.\n\n'
                    '**🏆 Monthly Competition**\n'
                    'Every month, the Top 10 most active players receive amazing in-game rewards including Gold, Hype Boxes, Crates, Tags, and more! Winners are announced on the last day of each month, and the leaderboard resets for the next competition.\n\n'
                    '**💡 Quick Tips**\n'
                    '• Use </level:1179528065643196557> to check your level and XP\n'
                    '• Play chat games and DM games to earn bonus XP\n'
                    '• Claim your daily reward with </daily:1457414301663887443> to maintain your streak\n'
                    '• Check your statistics with </statistics:1457409204829687820> to track your progress\n'
                    '• Check your milestones with </milestones:1457409204829687821> to track your progress\n'
                    'Click the **❓ Help** button below for detailed information and FAQs!'
                )
            )
            
            current_time = int(datetime.now(timezone.utc).timestamp())
            embed2 = discord.Embed(
                color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR')),
                title="Leaderboard <:minecadia_2:1444800686372950117>",
                description=(
                    await SendGamesView.get_leaderboard(interaction.guild, self.bot) +
                    f'\n\n**Last Updated** <t:{current_time}:R>\n\n'
                    f'✅ **Active DM Game**: {active}\n'
                    f'🚨 **Next DM Game**: <t:{new_dm_game}:R>\n'
                    f"-# {rotation_display}"
                )
            )
            # Only set thumbnail if logo is a valid URL (not a local file path)
            from utils.helpers import get_embed_logo_url
            logo_url = get_embed_logo_url("Assets/Logo.png")
            if logo_url:
                embed2.set_thumbnail(url=logo_url)
            embed2.set_image(url="https://i.imgur.com/z3bbBSA.png")
            footer_logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
            embed2.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=footer_logo_url)
            
            channel = interaction.channel
            if isinstance(channel, discord.TextChannel):
                # Add ViewMore buttons to the top embed
                from ui.sendgames_view import ViewMore
                view_more = ViewMore()
                
                await channel.send(embed=embed1, view=view_more)
                await channel.send(embed=embed2, view=DMGamesView(self.bot, active))
                await interaction.followup.send("`✅` Messages sent!", ephemeral=True)


async def setup(bot):
    await bot.add_cog(SendGames(bot))

