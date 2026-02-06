import discord
from core.config.manager import ConfigManager
from core.database.pool import DatabasePool
from ui.dm_games_view import DMGamesView
from pathlib import Path


class ViewMore(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.config = ConfigManager.get_instance()
        # Load winners data
        winners_path = Path(__file__).parent.parent / "assets" / "Configs" / "winners.json"
        import json
        with open(winners_path) as f:
            self.winners_data = json.load(f)
        
        # Add Changelog button (row 0)
        self.add_item(self.changelog_button())
        # Add Rewards button (row 0)
        self.add_item(self.rewards_button())
        # Help, All Time Leaderboard, Past Winners, Past Games are added via decorators
    
    @discord.ui.button(label="Help", emoji="❓", custom_id="leveling_help", style=discord.ButtonStyle.green, row=0)
    async def help_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        help_embed = discord.Embed(
            title="❓ Leveling System Help & FAQ",
            color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR')),
            description=(
                '**What are levels?**\n'
                'Your level indicates your activity in our Discord. Activity is determined by how often you type in various chats, react to messages, win mini-games, and much more. Spamming chats is prohibited and rewards will be stripped as punishment for doing so.\n\n'
                
                '**How do I check my level?**\n'
                'You can check your level by typing </level:1179528065643196557> in any channel that you can type in.\n\n'
                
                '**What does my level mean?**\n'
                'Every month the Top 10 most active players in the Discord will receive in game rewards on the server. The leaderboard below updates frequently and displays who our most active players in the Discord are. At the end of the month winners are announced and given their in game reward and the leaderboards resets back to 0.\n\n'
                
                '**How do I redeem my reward?**\n'
                'A ticket will automatically be opened for you when the rewards are announced. From there, please provide which rewards you want, what IGN it will be going to, and which server it will be on.\n\n'
                
                '**How do I get the Games Notification Role?**\n'
                'You can get notified for every single game that is sent by heading over to https://discord.com/channels/680569558754656280/922146090504032286/1190636859009814598 and clicking on __Roles__. Then, a menu to gain some notification roles will appear. Click the drop down and select __Games__ at the bottom (along with any other roles you want.)\n\n'
                
                '**TIP:** Type </level:1179528065643196557> in any channel to view how many levels you have. :gift:'
            )
        )
        from utils.helpers import get_embed_logo_url
        logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
        help_embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
        await interaction.response.send_message(embed=help_embed, ephemeral=True)
    
    def changelog_button(self):
        return discord.ui.Button(
            style=discord.ButtonStyle.url,
            url="https://discord.com/channels/680569558754656280/1191466240909246564",
            label="Changelog",
            emoji="📜",
            row=0
        )
    
    def rewards_button(self):
        button = discord.ui.Button(
            emoji="🎁",
            label="Rewards",
            style=discord.ButtonStyle.grey,
            custom_id="rewards_button",
            row=0
        )
        
        async def callback(interaction: discord.Interaction):
            from pathlib import Path
            import json
            import re
            # Support both old (winners.json) and new (rewards.json) structure
            winners_file = Path(__file__).parent.parent / "assets" / "Configs" / "rewards.json"
            if not winners_file.exists():
                winners_file = Path(__file__).parent.parent / "assets" / "Configs" / "winners.json"
            
            with open(winners_file, 'r') as file:
                data = json.load(file)
                # Support both old (Rewards) and new (rewards.positions) structure
                rewards_dict = data.get("Rewards", {}) or data.get("rewards", {}).get("positions", {})
                rewards = {
                    k: re.sub(r"<@\{user_id\}> \u00bb ", "", v)
                    for k, v in rewards_dict.items()
                    if k not in ["title", "footer"]
                }
                await interaction.response.send_message(
                    content="\n".join(rewards.values()),
                    ephemeral=True
                )
        
        button.callback = callback
        return button
    
    @discord.ui.button(label="All Time Leaderboard", emoji="🏆", custom_id="all_time_leaderboard", style=discord.ButtonStyle.grey, row=1)
    async def all_time_leaderboard(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            from ui.all_time_leaderboard import AllTimeLeaderboardView
            
            # Defer first to prevent timeout
            await interaction.response.defer(ephemeral=True)
            
            view = AllTimeLeaderboardView(interaction.client, interaction.guild)
            await view.send_leaderboard(interaction, "all_time_xp")
        except Exception as e:
            import traceback
            from core.logging.setup import get_logger
            logger = get_logger("Commands")
            logger.error(f"Error in all_time_leaderboard button: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(f"`❌` Error opening leaderboard: {str(e)}", ephemeral=True)
                else:
                    await interaction.response.send_message(f"`❌` Error opening leaderboard: {str(e)}", ephemeral=True)
            except Exception as e2:
                logger.error(f"Error sending error message: {e2}")
    
    @discord.ui.button(label="Past Winners", emoji="📊", custom_id="past_winners", style=discord.ButtonStyle.grey, row=1)
    async def past_winners(self, interaction: discord.Interaction, button: discord.ui.Button):
        from utils.paginator import Paginator
        from core.logging.setup import get_logger
        logger = get_logger("UI")
        
        try:
            await interaction.response.defer(ephemeral=True)
            
            # Create paginator for past winners by month
            paginator = Paginator()
            paginator.title = f"Leveling Leaderboard <:minecadia_2:1444800686372950117>"
            paginator.sep = 1  # 1 month per page
            paginator.ephemeral = True  # Mark as ephemeral
            
            from managers.milestones import MilestonesManager
            milestones_manager = MilestonesManager()
            
            data: list = []
            for month in list(self.winners_data['Months'].keys()):
                month_string: str = ""
                month_string += self.winners_data['Message_Formats']['title'].replace("{month}", month)
                
                # Process each winner with badge
                for index, user_id in enumerate(self.winners_data['Months'][month].keys(), 1):
                    # Get badge emoji
                    badge_emoji = await milestones_manager.get_display_badge(int(user_id), interaction.guild)
                    badge_text = f"{badge_emoji} " if badge_emoji else ""
                    
                    # Get format string (support both old and new structure)
                    format_str = None
                    if 'Message_Formats' in self.winners_data:
                        format_str = self.winners_data['Message_Formats'].get(str(index), "")
                    elif 'message_format' in self.winners_data:
                        positions = self.winners_data.get('message_format', {}).get('positions', {})
                        format_str = positions.get(str(index), "")
                    
                    if not format_str:
                        format_str = f"**{index}.** <@{user_id}> » Level {{level}}\n"
                    
                    # Replace placeholders
                    winner_line = format_str.replace("{user_id}", user_id).replace(
                        "{level}", str(self.winners_data['Months'][month][user_id])
                    )
                    
                    # Add badge before user mention (before the <@)
                    if "<@" in winner_line:
                        # Find position of <@ and insert badge before it
                        at_pos = winner_line.find("<@")
                        winner_line = winner_line[:at_pos] + badge_text + winner_line[at_pos:]
                    else:
                        # Fallback: add badge at start
                        winner_line = f"{badge_text}{winner_line}"
                    
                    month_string += winner_line
                
                data.append(month_string)
            
            paginator.data = data
            paginator.current_page = 1
            
            # Send the paginator directly in the ephemeral response
            await paginator.send(interaction)
        except Exception as e:
            logger.error(f"Error in past_winners button: {e}")
            import traceback
            logger.error(traceback.format_exc())
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(f"`❌` Error loading past winners: {str(e)}", ephemeral=True)
                else:
                    await interaction.response.send_message(f"`❌` Error loading past winners: {str(e)}", ephemeral=True)
            except Exception as e2:
                logger.error(f"Error sending error message: {e2}")
    
    @discord.ui.button(label="Past Games", emoji="🎮", custom_id="past_games", style=discord.ButtonStyle.grey, row=1)
    async def past_games(self, interaction: discord.Interaction, button: discord.ui.Button):
        from utils.paginator import Paginator
        from utils.helpers import get_recent_games
        from core.database.pool import DatabasePool
        
        games_str, games_list = await get_recent_games()
        
        # Get game_ids for dropdown
        db = await DatabasePool.get_instance()
        game_ids = await db.execute("SELECT game_id, game_name, refreshed_at, dm_game FROM games ORDER BY refreshed_at DESC LIMIT 100")
        
        paginator = Paginator()
        paginator.title = "Recent Games"
        paginator.data = games_str
        paginator.games = games_list
        paginator.game_ids = game_ids  # Add game_ids for dropdown
        paginator.sep = 15
        paginator.ephemeral = True  # Mark as ephemeral
        
        # Send the paginator directly in the ephemeral response
        await paginator.send(interaction)


class SendGamesView:
    # Emoji mapping for leaderboard positions
    POSITION_EMOJIS = {
        1: "<:minecadia_one:1111028062981718026>",
        2: "<:minecadia_two:1111028088546021466>",
        3: "<:minecadia_three:1111028142430228520>",
        4: "<:minecadia_four:1186027785735643216>",
        5: "<:minecadia_five:1186027816156930058>",
        6: "<:minecadia_six:1186027855210106880>",
        7: "<:minecadia_seven:1186027891989938226>",
        8: "<:minecadia_eight:1186027893285986314>",
        9: "<:minecadia_nine:1186027895508963439>",
        10: "<:minecadia_ten:1186027950689239190>"
    }
    
    @staticmethod
    async def get_leaderboard(guild: discord.Guild, bot) -> str:
        from managers.milestones import MilestonesManager
        milestones_manager = MilestonesManager()
        
        import asyncio
        db = await asyncio.wait_for(DatabasePool.get_instance(), timeout=5.0)
        # Cast to ensure proper numeric sorting
        rows = await asyncio.wait_for(
            db.execute(
                "SELECT user_id, level, xp FROM leveling ORDER BY CAST(level AS UNSIGNED) DESC, CAST(xp AS UNSIGNED) DESC LIMIT 10"
            ),
            timeout=5.0
        )
        
        leaderboard = []
        for index, row in enumerate(rows, 1):
            user_id = int(row['user_id'])
            user = bot.get_user(user_id)
            
            # Fallback to fetching from guild if not in cache
            if not user and guild:
                user = guild.get_member(user_id)
            
            # Get badge emoji
            badge_emoji = await milestones_manager.get_display_badge(user_id, guild)
            badge_text = f"{badge_emoji} " if badge_emoji else ""
            
            if user:
                emoji = SendGamesView.POSITION_EMOJIS.get(index, f"**{index}.**")
                leaderboard.append(f"{emoji} {badge_text}{user.mention} » Level {row['level']} ({row['xp']} XP)")
            else:
                # Fallback to user ID mention if user not found
                emoji = SendGamesView.POSITION_EMOJIS.get(index, f"**{index}.**")
                leaderboard.append(f"{emoji} {badge_text}<@{user_id}> » Level {row['level']} ({row['xp']} XP)")
        
        return "\n".join(leaderboard) if leaderboard else "No data available."
    
    @staticmethod
    async def get_full_leaderboard(guild: discord.Guild, bot) -> list:
        """Get the full leaderboard as a list of strings for pagination."""
        from managers.milestones import MilestonesManager
        milestones_manager = MilestonesManager()
        
        db = await DatabasePool.get_instance()
        # Cast to ensure proper numeric sorting, limit to top 200 for performance
        rows = await db.execute(
            "SELECT user_id, level, xp FROM leveling ORDER BY CAST(level AS UNSIGNED) DESC, CAST(xp AS UNSIGNED) DESC LIMIT 200"
        )
        
        if not rows:
            return ["No data available."]
        
        # Batch fetch all badge preferences and achievements
        user_ids = [str(row['user_id']) for row in rows]
        
        # Get all selected badges in one query using parameterized query
        selected_badge_map = {}
        if user_ids:
            placeholders = ','.join(['%s'] * len(user_ids))
            selected_badges = await db.execute(
                f"SELECT user_id, selected_badge_id FROM user_badge_preferences WHERE user_id IN ({placeholders})",
                tuple(user_ids)
            )
            selected_badge_map = {row['user_id']: row['selected_badge_id'] for row in selected_badges}
        
        # Get all achievements for all users in one query
        user_achievements_map = {}
        if user_ids:
            placeholders = ','.join(['%s'] * len(user_ids))
            all_achievements = await db.execute(
                f"SELECT user_id, achievement_id FROM user_achievements WHERE user_id IN ({placeholders})",
                tuple(user_ids)
            )
            
            # Group achievements by user_id
            for row in all_achievements:
                user_id = row['user_id']
                if user_id not in user_achievements_map:
                    user_achievements_map[user_id] = []
                user_achievements_map[user_id].append(row['achievement_id'])
        
        # Build badge map by processing achievements in memory
        user_badges_map = {}
        
        # For each user, find their highest priority badge
        for user_id_str in user_ids:
            achievements_list = user_achievements_map.get(user_id_str, [])
            if not achievements_list:
                continue
            
            # Map achievement_ids to milestone data
            badge_map = {}
            for achievement_id in achievements_list:
                milestone = milestones_manager._find_milestone_by_id(achievement_id)
                if milestone:
                    game_type = milestone.get('game_type', '')
                    metric = milestone.get('metric', '')
                    key = f"{game_type}:{metric}"
                    threshold = milestone.get('threshold', 0)
                    
                    if key not in badge_map or threshold > badge_map[key].get('threshold', 0):
                        badge_map[key] = milestone
            
            # Get highest priority badge
            if badge_map:
                badges = list(badge_map.values())
                badges.sort(key=lambda x: (x.get('threshold', 0), x.get('game_type', '')), reverse=True)
                user_badges_map[user_id_str] = badges[0]
        
        leaderboard = []
        for index, row in enumerate(rows, 1):
            user_id = int(row['user_id'])
            user_id_str = str(user_id)
            user = bot.get_user(user_id)
            
            # Fallback to fetching from guild if not in cache
            if not user and guild:
                user = guild.get_member(user_id)
            
            # Get badge emoji from cached data
            badge_emoji = None
            selected_badge_id = selected_badge_map.get(user_id_str)
            if selected_badge_id and selected_badge_id in user_achievements_map.get(user_id_str, []):
                milestone = milestones_manager._find_milestone_by_id(selected_badge_id)
                if milestone:
                    emoji_str = milestone.get('emoji')
                    if emoji_str:
                        badge_emoji = milestones_manager._resolve_emoji(emoji_str, guild)
            
            if not badge_emoji and user_id_str in user_badges_map:
                badge = user_badges_map[user_id_str]
                if badge:
                    emoji_str = badge.get('emoji')
                    if emoji_str:
                        badge_emoji = milestones_manager._resolve_emoji(emoji_str, guild)
            
            badge_text = f"{badge_emoji} " if badge_emoji else ""
            
            if user:
                # Use emoji for positions 1-10, otherwise use number
                if index <= 10:
                    emoji = SendGamesView.POSITION_EMOJIS.get(index, f"**{index}.**")
                    leaderboard.append(f"{emoji} {badge_text}{user.mention} » Level {row['level']} ({row['xp']} XP)")
                else:
                    leaderboard.append(f"**{index}.** {badge_text}{user.mention} » Level {row['level']} ({row['xp']} XP)")
            else:
                # User not found, use user ID
                if index <= 10:
                    emoji = SendGamesView.POSITION_EMOJIS.get(index, f"**{index}.**")
                    leaderboard.append(f"{emoji} {badge_text}<@{user_id}> » Level {row['level']} ({row['xp']} XP)")
                else:
                    leaderboard.append(f"**{index}.** {badge_text}<@{user_id}> » Level {row['level']} ({row['xp']} XP)")
        
        return leaderboard if leaderboard else ["No data available."]

