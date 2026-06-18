import discord
from core.database.pool import DatabasePool


class SendGamesView(discord.ui.View):
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
        # Numeric columns sort correctly without CAST once idx_leveling_rank exists
        rows = await asyncio.wait_for(
            db.execute(
                "SELECT user_id, level, xp FROM leveling ORDER BY level DESC, xp DESC LIMIT 10"
            ),
            timeout=5.0
        )

        # Try to fetch active (this month) and total historical participants counts.
        active_count = 0
        total_players = 0
        try:
            r = await db.execute("SELECT COUNT(*) as count FROM leveling WHERE is_active = 1")
            if r:
                active_count = int(r[0].get('count', 0))
        except Exception:
            active_count = 0

        try:
            r2 = await db.execute("SELECT COUNT(*) as count FROM leveling WHERE ever_played = 1")
            if r2:
                total_players = int(r2[0].get('count', 0))
        except Exception:
            total_players = 0
        
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
        
        header = f"Active this month: {active_count} | Total players: {total_players}\n\n"
        return header + ("\n".join(leaderboard) if leaderboard else "No data available.")
    
    @staticmethod
    async def get_full_leaderboard(guild: discord.Guild, bot) -> list:
        """Get the full leaderboard as a list of strings for pagination."""
        from managers.milestones import MilestonesManager
        milestones_manager = MilestonesManager()
        
        db = await DatabasePool.get_instance()
        rows = await db.execute(
            "SELECT user_id, level, xp FROM leveling ORDER BY level DESC, xp DESC LIMIT 200"
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
