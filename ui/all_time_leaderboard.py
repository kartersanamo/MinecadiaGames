import discord
from core.database.pool import DatabasePool
from core.config.manager import ConfigManager
from managers.milestones import MilestonesManager

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
        logo_url = self.bot.app.embeds.get_logo_url(self.config.get('config', 'LOGO'))
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
            logo_url = self.bot.app.embeds.get_logo_url(self.config.get('config', 'LOGO'))
            error_embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
            await loading_msg.edit(embed=error_embed)
            return
        
        # Create paginator with message reference
        from ui.all_time_leaderboard_alltimeleaderboardpaginator import (
            AllTimeLeaderboardPaginator,
        )

        paginator = AllTimeLeaderboardPaginator(
            self, leaderboard_type, leaderboard_data, message=loading_msg
        )
        
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
            "mastermind_wins": "Mastermind Wins",
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
                "hangman_wins": "Hangman",
                "mastermind_wins": "Mastermind"
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
        """Global level = sum of each user's level at every monthly /wipe-levels."""
        from managers.global_level import ensure_global_level_table

        await ensure_global_level_table(db)
        rows = await db.execute(
            """
            SELECT user_id, global_level
            FROM leveling_global
            WHERE global_level > 0
            ORDER BY global_level DESC
            LIMIT 500
            """
        )

        if not rows:
            return ["No data available. Levels are added here after each monthly wipe."]

        user_ids = [str(row["user_id"]) for row in rows]
        
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
            user_id = int(row["user_id"])
            user_id_str = str(user_id)
            level = int(row["global_level"])

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
                leaderboard.append(
                    f"**{index}.** {badge_text}{user.mention} » Global Level {level}"
                )
            else:
                leaderboard.append(
                    f"**{index}.** {badge_text}<@{user_id}> » Global Level {level}"
                )
        
        return leaderboard if leaderboard else ["No data available."]
    
    async def _get_game_wins_leaderboard(self, db: DatabasePool, game_name: str) -> list:
        """Get all-time wins leaderboard for a specific game"""
        from repositories.game_session_repository import normalize_game_type

        dm_game_types = {
            "Tictactoe": "tictactoe",
            "TicTacToe": "tictactoe",
            "Wordle": "wordle",
            "Connect Four": "connect_four",
            "Memory": "memory",
            "2048": "2048",
            "Minesweeper": "minesweeper",
            "Hangman": "hangman",
            "Filler": "filler",
            "Mastermind": "mastermind",
        }
        
        # Chat games use xp_logs (every entry is a win)
        chat_games = ["Trivia", "Math Quiz", "Flag Guesser", "Unscramble", "Emoji Quiz", "Fill in the Blank"]
        
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
        elif game_name in dm_game_types:
            game_type = normalize_game_type(dm_game_types[game_name])
            try:
                rows = await db.execute(
                    """
                    SELECT user_id, COUNT(*) AS wins
                    FROM game_sessions
                    WHERE game_type = %s AND status = 'won'
                    GROUP BY user_id
                    ORDER BY wins DESC
                    LIMIT 500
                    """,
                    (game_type,),
                )
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
            SELECT user_id,
                   MAX(CAST(JSON_UNQUOTE(JSON_EXTRACT(stats, '$.score')) AS UNSIGNED)) AS best_score
            FROM game_sessions
            WHERE game_type = '2048'
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
