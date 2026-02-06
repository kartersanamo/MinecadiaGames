import discord
from core.database.pool import DatabasePool
from core.config.manager import ConfigManager
from managers.milestones import MilestonesManager
from utils.paginator import Paginator
from typing import Optional


class AllTimeLeaderboardView(discord.ui.View):
    def __init__(self, bot, guild: discord.Guild):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild = guild
        self.config = ConfigManager.get_instance()
        self.milestones_manager = MilestonesManager()
    
    async def send_leaderboard(self, interaction: discord.Interaction, leaderboard_type: str = "all_time_xp"):
        """Send the all-time leaderboard"""
        # Note: interaction.response should already be deferred by the caller
        
        # Send loading message first
        loading_embed = discord.Embed(
            title="🏆 All Time Leaderboard",
            description="⏳ Loading leaderboard data... Please wait.",
            color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR'))
        )
        from utils.helpers import get_embed_logo_url
        logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
        loading_embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
        loading_msg = await interaction.followup.send(embed=loading_embed, ephemeral=True, wait=True)
        
        # Get leaderboard data (this is the slow part)
        leaderboard_data = await self.get_all_time_leaderboard(leaderboard_type)
        
        if not leaderboard_data:
            error_embed = discord.Embed(
                title="🏆 All Time Leaderboard",
                description="No leaderboard data available.",
                color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR'))
            )
            from utils.helpers import get_embed_logo_url
            logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
            error_embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
            await loading_msg.edit(embed=error_embed)
            return
        
        # Create paginator with message reference
        paginator = AllTimeLeaderboardPaginator(self, leaderboard_type, leaderboard_data, message=loading_msg)
        
        # Edit the loading message with the actual leaderboard
        embed = paginator.create_embed()
        paginator.update_buttons()
        await loading_msg.edit(embed=embed, view=paginator)
    
    def _get_leaderboard_title(self, leaderboard_type: str) -> str:
        """Get display title for leaderboard type"""
        titles = {
            "all_time_xp": "Total XP",
            "all_time_level": "Highest Level",
            "trivia_wins": "Trivia Wins",
            "math_quiz_wins": "Math Quiz Wins",
            "flag_guesser_wins": "Flag Guesser Wins",
            "unscramble_wins": "Unscramble Wins",
            "emoji_quiz_wins": "Emoji Quiz Wins",
            "tictactoe_wins": "TicTacToe Wins",
            "wordle_wins": "Wordle Wins",
            "connect_four_wins": "Connect Four Wins",
            "memory_wins": "Memory Wins",
            "2048_wins": "2048 Wins",
            "minesweeper_wins": "Minesweeper Wins",
            "hangman_wins": "Hangman Wins",
            "2048_best_score": "2048 Best Score"
        }
        return titles.get(leaderboard_type, leaderboard_type.replace("_", " ").title())
    
    async def get_all_time_leaderboard(self, leaderboard_type: str) -> list:
        """Get all-time leaderboard data for a specific type"""
        db = await DatabasePool.get_instance()
        
        if leaderboard_type == "all_time_xp":
            return await self._get_all_time_xp_leaderboard(db)
        elif leaderboard_type == "all_time_level":
            return await self._get_all_time_level_leaderboard(db)
        elif leaderboard_type.endswith("_wins"):
            # Map leaderboard type to game name
            game_name_map = {
                "trivia_wins": "Trivia",
                "math_quiz_wins": "Math Quiz",
                "flag_guesser_wins": "Flag Guesser",
                "unscramble_wins": "Unscramble",
                "emoji_quiz_wins": "Emoji Quiz",
                "tictactoe_wins": "TicTacToe",
                "wordle_wins": "Wordle",
                "connect_four_wins": "Connect Four",
                "memory_wins": "Memory",
                "2048_wins": "2048",
                "minesweeper_wins": "Minesweeper",
                "hangman_wins": "Hangman"
            }
            game_name = game_name_map.get(leaderboard_type, leaderboard_type.replace("_wins", "").replace("_", " ").title())
            return await self._get_game_wins_leaderboard(db, game_name)
        elif leaderboard_type == "2048_best_score":
            return await self._get_2048_best_score_leaderboard(db)
        else:
            return []
    
    async def _get_all_time_xp_leaderboard(self, db: DatabasePool) -> list:
        """Get all-time total XP leaderboard"""
        # Sum all XP from xp_logs (this is all-time, not reset monthly)
        # Limit to top 500 for performance
        rows = await db.execute(
            """
            SELECT user_id, SUM(xp) as total_xp
            FROM xp_logs
            GROUP BY user_id
            ORDER BY total_xp DESC
            LIMIT 500
            """
        )
        
        if not rows:
            return ["No data available."]
        
        # Batch fetch all badge preferences and achievements
        user_ids = [str(row['user_id']) for row in rows]
        
        # Get all selected badges in one query
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
                milestone = self.milestones_manager._find_milestone_by_id(achievement_id)
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
            user = self.bot.get_user(user_id)
            
            if not user and self.guild:
                user = self.guild.get_member(user_id)
            
            # Get badge emoji from cached data
            badge_emoji = None
            selected_badge_id = selected_badge_map.get(user_id_str)
            if selected_badge_id and selected_badge_id in user_achievements_map.get(user_id_str, []):
                milestone = self.milestones_manager._find_milestone_by_id(selected_badge_id)
                if milestone:
                    emoji_str = milestone.get('emoji')
                    if emoji_str:
                        badge_emoji = self.milestones_manager._resolve_emoji(emoji_str, self.guild)
            
            if not badge_emoji and user_id_str in user_badges_map:
                badge = user_badges_map[user_id_str]
                if badge:
                    emoji_str = badge.get('emoji')
                    if emoji_str:
                        badge_emoji = self.milestones_manager._resolve_emoji(emoji_str, self.guild)
            
            badge_text = f"{badge_emoji} " if badge_emoji else ""
            
            if user:
                leaderboard.append(f"**{index}.** {badge_text}{user.mention} » {int(row['total_xp']):,} XP")
            else:
                leaderboard.append(f"**{index}.** {badge_text}<@{user_id}> » {int(row['total_xp']):,} XP")
        
        return leaderboard if leaderboard else ["No data available."]
    
    async def _get_all_time_level_leaderboard(self, db: DatabasePool) -> list:
        """Get all-time highest level leaderboard"""
        # Get current levels (these reset monthly, but we can track all-time from xp_logs)
        # For all-time, we'll calculate level from total XP
        # Limit to top 500 for performance
        rows = await db.execute(
            """
            SELECT user_id, SUM(xp) as total_xp
            FROM xp_logs
            GROUP BY user_id
            ORDER BY total_xp DESC
            LIMIT 500
            """
        )
        
        if not rows:
            return ["No data available."]
        
        # Get level requirements
        level_data = self.config.get('levels', {})
        levels_dict = level_data.get('LEVELS', {}) or level_data.get('levels', {})
        
        # Batch fetch all badge preferences and achievements
        user_ids = [str(row['user_id']) for row in rows]
        
        # Get all selected badges in one query
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
                milestone = self.milestones_manager._find_milestone_by_id(achievement_id)
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
            total_xp = int(row['total_xp'])
            
            # Calculate level from total XP
            level = 1
            for lvl in sorted([int(k) for k in levels_dict.keys()], reverse=True):
                required_xp = levels_dict.get(str(lvl), 0)
                if total_xp >= required_xp:
                    level = lvl
                    break
            
            user = self.bot.get_user(user_id)
            if not user and self.guild:
                user = self.guild.get_member(user_id)
            
            # Get badge emoji from cached data
            badge_emoji = None
            selected_badge_id = selected_badge_map.get(user_id_str)
            if selected_badge_id and selected_badge_id in user_achievements_map.get(user_id_str, []):
                milestone = self.milestones_manager._find_milestone_by_id(selected_badge_id)
                if milestone:
                    emoji_str = milestone.get('emoji')
                    if emoji_str:
                        badge_emoji = self.milestones_manager._resolve_emoji(emoji_str, self.guild)
            
            if not badge_emoji and user_id_str in user_badges_map:
                badge = user_badges_map[user_id_str]
                if badge:
                    emoji_str = badge.get('emoji')
                    if emoji_str:
                        badge_emoji = self.milestones_manager._resolve_emoji(emoji_str, self.guild)
            
            badge_text = f"{badge_emoji} " if badge_emoji else ""
            
            if user:
                leaderboard.append(f"**{index}.** {badge_text}{user.mention} » Level {level} ({total_xp:,} XP)")
            else:
                leaderboard.append(f"**{index}.** {badge_text}<@{user_id}> » Level {level} ({total_xp:,} XP)")
        
        return leaderboard if leaderboard else ["No data available."]
    
    async def _get_game_wins_leaderboard(self, db: DatabasePool, game_name: str) -> list:
        """Get all-time wins leaderboard for a specific game"""
        # Map game names to table names
        table_map = {
            "Tictactoe": ("users_tictactoe", "won", "Won"),
            "TicTacToe": ("users_tictactoe", "won", "Won"),
            "Wordle": ("users_wordle", "won", "Won"),
            "Connect Four": ("users_connectfour", "status", "Won"),
            "Memory": ("users_memory", "won", "Won"),
            "2048": ("users_2048", "status", "Won"),
            "Minesweeper": ("users_minesweeper", "won", "Won"),
            "Hangman": ("users_hangman", "won", "Won")
        }
        
        # Chat games use xp_logs (every entry is a win)
        chat_games = ["Trivia", "Math Quiz", "Flag Guesser", "Unscramble", "Emoji Quiz"]
        
        # Normalize game name
        if game_name == "Tictactoe":
            game_name = "TicTacToe"
        
        if game_name in chat_games:
            rows = await db.execute(
                """
                SELECT user_id, COUNT(*) as wins
                FROM xp_logs
                WHERE source = %s
                GROUP BY user_id
                ORDER BY wins DESC
                LIMIT 500
                """,
                (game_name,)
            )
        elif game_name in table_map:
            table_name, status_field, win_value = table_map[game_name]
            try:
                # Use parameterized query to avoid SQL injection
                # Note: table_name and status_field cannot be parameterized, but win_value can
                query = f"""
                    SELECT user_id, COUNT(*) as wins
                    FROM {table_name}
                    WHERE {status_field} = %s
                    GROUP BY user_id
                    ORDER BY wins DESC
                    LIMIT 500
                """
                rows = await db.execute(query, (win_value,))
            except Exception as e:
                from core.logging.setup import get_logger
                logger = get_logger("UI")
                logger.error(f"Error querying {game_name} wins leaderboard: {e}")
                return ["No data available."]
        else:
            return ["No data available."]
        
        if not rows:
            return ["No data available."]
        
        # Batch fetch all badge preferences and achievements
        user_ids = [str(row['user_id']) for row in rows]
        
        # Get all selected badges in one query
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
                milestone = self.milestones_manager._find_milestone_by_id(achievement_id)
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
            wins = int(row['wins'])
            
            user = self.bot.get_user(user_id)
            if not user and self.guild:
                user = self.guild.get_member(user_id)
            
            # Get badge emoji from cached data
            badge_emoji = None
            selected_badge_id = selected_badge_map.get(user_id_str)
            if selected_badge_id and selected_badge_id in user_achievements_map.get(user_id_str, []):
                milestone = self.milestones_manager._find_milestone_by_id(selected_badge_id)
                if milestone:
                    emoji_str = milestone.get('emoji')
                    if emoji_str:
                        badge_emoji = self.milestones_manager._resolve_emoji(emoji_str, self.guild)
            
            if not badge_emoji and user_id_str in user_badges_map:
                badge = user_badges_map[user_id_str]
                if badge:
                    emoji_str = badge.get('emoji')
                    if emoji_str:
                        badge_emoji = self.milestones_manager._resolve_emoji(emoji_str, self.guild)
            
            badge_text = f"{badge_emoji} " if badge_emoji else ""
            
            if user:
                leaderboard.append(f"**{index}.** {badge_text}{user.mention} » {wins:,} wins")
            else:
                leaderboard.append(f"**{index}.** {badge_text}<@{user_id}> » {wins:,} wins")
        
        return leaderboard if leaderboard else ["No data available."]
    
    async def _get_2048_best_score_leaderboard(self, db: DatabasePool) -> list:
        """Get all-time 2048 best score leaderboard"""
        rows = await db.execute(
            """
            SELECT user_id, MAX(score) as best_score
            FROM users_2048
            GROUP BY user_id
            ORDER BY best_score DESC
            LIMIT 500
            """
        )
        
        if not rows:
            return ["No data available."]
        
        # Batch fetch all badge preferences and achievements
        user_ids = [str(row['user_id']) for row in rows]
        
        # Get all selected badges in one query
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
                milestone = self.milestones_manager._find_milestone_by_id(achievement_id)
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
            best_score = int(row['best_score'] or 0)
            
            user = self.bot.get_user(user_id)
            if not user and self.guild:
                user = self.guild.get_member(user_id)
            
            # Get badge emoji from cached data
            badge_emoji = None
            selected_badge_id = selected_badge_map.get(user_id_str)
            if selected_badge_id and selected_badge_id in user_achievements_map.get(user_id_str, []):
                milestone = self.milestones_manager._find_milestone_by_id(selected_badge_id)
                if milestone:
                    emoji_str = milestone.get('emoji')
                    if emoji_str:
                        badge_emoji = self.milestones_manager._resolve_emoji(emoji_str, self.guild)
            
            if not badge_emoji and user_id_str in user_badges_map:
                badge = user_badges_map[user_id_str]
                if badge:
                    emoji_str = badge.get('emoji')
                    if emoji_str:
                        badge_emoji = self.milestones_manager._resolve_emoji(emoji_str, self.guild)
            
            badge_text = f"{badge_emoji} " if badge_emoji else ""
            
            if user:
                leaderboard.append(f"**{index}.** {badge_text}{user.mention} » {best_score:,} points")
            else:
                leaderboard.append(f"**{index}.** {badge_text}<@{user_id}> » {best_score:,} points")
        
        return leaderboard if leaderboard else ["No data available."]


class AllTimeLeaderboardPaginator(Paginator):
    def __init__(self, parent_view: AllTimeLeaderboardView, leaderboard_type: str, leaderboard_data: list, message: Optional[discord.Message] = None):
        super().__init__(timeout=900)
        self.parent_view = parent_view
        self.leaderboard_type = leaderboard_type
        self.title = f"🏆 All Time Leaderboard - {parent_view._get_leaderboard_title(leaderboard_type)}"
        self.data = leaderboard_data
        self.sep = 20  # 20 entries per page
        self.ephemeral = True
        self._message = message  # Store message reference for editing
        
        # Add select menu
        self.add_item(AllTimeLeaderboardSelect(self))
    
    async def update_message(self, interaction: discord.Interaction):
        """Override to use stored message reference if available"""
        self.update_buttons()
        embed = self.create_embed()
        
        # If we have a stored message reference, use it (for the loading message we edited)
        if self._message:
            await self._message.edit(embed=embed, view=self)
        else:
            # Fall back to default behavior
            if self.ephemeral:
                await interaction.edit_original_response(embed=embed, view=self)
            else:
                await interaction.message.edit(embed=embed, view=self)
    
    async def update_leaderboard_type(self, interaction: discord.Interaction, new_type: str):
        """Update the leaderboard type and refresh the display"""
        await interaction.response.defer(ephemeral=True)
        
        # Get new leaderboard data
        leaderboard_data = await self.parent_view.get_all_time_leaderboard(new_type)
        
        if not leaderboard_data:
            await interaction.followup.send("No leaderboard data available.", ephemeral=True)
            return
        
        # Update paginator
        self.leaderboard_type = new_type
        self.title = f"🏆 All Time Leaderboard - {self.parent_view._get_leaderboard_title(new_type)}"
        self.data = leaderboard_data
        self.current_page = 1
        
        # Update display
        self.update_buttons()
        embed = self.create_embed()
        # Use stored message reference if available, otherwise use edit_original_response
        if self._message:
            await self._message.edit(embed=embed, view=self)
        else:
            await interaction.edit_original_response(embed=embed, view=self)


class AllTimeLeaderboardSelect(discord.ui.Select):
    def __init__(self, paginator: AllTimeLeaderboardPaginator):
        self.paginator = paginator
        
        options = [
            discord.SelectOption(
                label="All Time XP",
                value="all_time_xp",
                description="Total XP earned across all time",
                emoji="💰"
            ),
            discord.SelectOption(
                label="All Time Level",
                value="all_time_level",
                description="Highest level achieved (calculated from total XP)",
                emoji="⭐"
            ),
            discord.SelectOption(
                label="Trivia Wins",
                value="trivia_wins",
                description="Total Trivia games won",
                emoji="❓"
            ),
            discord.SelectOption(
                label="Math Quiz Wins",
                value="math_quiz_wins",
                description="Total Math Quiz games won",
                emoji="➕"
            ),
            discord.SelectOption(
                label="Flag Guesser Wins",
                value="flag_guesser_wins",
                description="Total Flag Guesser games won",
                emoji="🏳️"
            ),
            discord.SelectOption(
                label="Unscramble Wins",
                value="unscramble_wins",
                description="Total Unscramble games won",
                emoji="🔤"
            ),
            discord.SelectOption(
                label="Emoji Quiz Wins",
                value="emoji_quiz_wins",
                description="Total Emoji Quiz games won",
                emoji="😀"
            ),
            discord.SelectOption(
                label="TicTacToe Wins",
                value="tictactoe_wins",
                description="Total TicTacToe games won",
                emoji="⭕"
            ),
            discord.SelectOption(
                label="Wordle Wins",
                value="wordle_wins",
                description="Total Wordle games won",
                emoji="📝"
            ),
            discord.SelectOption(
                label="Connect Four Wins",
                value="connect_four_wins",
                description="Total Connect Four games won",
                emoji="❌"
            ),
            discord.SelectOption(
                label="Memory Wins",
                value="memory_wins",
                description="Total Memory games won",
                emoji="🧠"
            ),
            discord.SelectOption(
                label="2048 Wins",
                value="2048_wins",
                description="Total 2048 games won (reached 2048 tile)",
                emoji="🔢"
            ),
            discord.SelectOption(
                label="Minesweeper Wins",
                value="minesweeper_wins",
                description="Total Minesweeper games won",
                emoji="💣"
            ),
            discord.SelectOption(
                label="Hangman Wins",
                value="hangman_wins",
                description="Total Hangman games won",
                emoji="🪢"
            ),
            discord.SelectOption(
                label="2048 Best Score",
                value="2048_best_score",
                description="Best score achieved in 2048",
                emoji="🎯"
            ),
        ]
        
        super().__init__(
            placeholder="Select leaderboard type...",
            options=options,
            row=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle select menu selection"""
        leaderboard_type = self.values[0]
        await self.paginator.update_leaderboard_type(interaction, leaderboard_type)

