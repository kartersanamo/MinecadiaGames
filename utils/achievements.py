"""Utility functions for checking and awarding achievements"""
from managers.milestones import MilestonesManager
from managers.leveling import LevelingManager
from core.database.pool import DatabasePool
import discord


def _calculate_milestone_xp(milestone: dict, all_milestones: list) -> int:
    """Calculate XP reward for a milestone based on its tier/position"""
    # Sort milestones by threshold to get tier order
    sorted_milestones = sorted(all_milestones, key=lambda x: x.get('threshold', 0))
    
    # Find the position/index of this milestone (0-based)
    try:
        milestone_index = next(i for i, m in enumerate(sorted_milestones) if m.get('id') == milestone.get('id'))
    except StopIteration:
        milestone_index = 0
    
    # Calculate XP: base 400 + (tier * scaling factor)
    # Scale from 400 to 700 based on position
    # If there's only 1 milestone, give 550 (middle)
    total_milestones = len(sorted_milestones)
    if total_milestones == 1:
        xp = 550
    else:
        # Scale from 400 to 700
        # Position 0 (first) = 400, position last = 700
        base_xp = 400
        max_xp = 700
        xp_range = max_xp - base_xp
        
        # Linear scaling based on position
        if total_milestones > 1:
            progress = milestone_index / (total_milestones - 1)
            xp = int(base_xp + (xp_range * progress))
        else:
            xp = base_xp
    
    # Ensure it's within bounds
    xp = max(400, min(700, xp))
    return xp


async def check_game_achievements(user: discord.User, game_type: str, metric: str, value: int, channel: discord.TextChannel = None, bot = None):
    """Check and award achievements for a game metric"""
    milestones_manager = MilestonesManager()
    new_achievements = await milestones_manager.check_achievements(user.id, game_type, metric, value)
    
    if new_achievements:
        # Get all milestones for this metric to calculate XP tier
        milestones_config = milestones_manager.milestones_config
        game_milestones = milestones_config.get(game_type, {})
        metric_milestones = game_milestones.get(metric, [])
        
        # Get guild for emoji resolution
        guild = channel.guild if hasattr(channel, 'guild') else None if channel else None
        
        for achievement in new_achievements:
            # Calculate XP reward based on milestone tier
            milestone_xp = _calculate_milestone_xp(achievement, metric_milestones)
            
            # Award XP for the milestone
            try:
                # Try to get bot/client instance - prefer passed bot, then try from channel
                client = bot
                if not client and channel:
                    # Try to get client from channel's state
                    try:
                        if hasattr(channel, '_state'):
                            client = getattr(channel._state, '_client', None) or getattr(channel._state, 'client', None)
                    except:
                        pass
                    # If that doesn't work, try from guild
                    if not client and hasattr(channel, 'guild') and channel.guild:
                        try:
                            if hasattr(channel.guild, '_state'):
                                client = getattr(channel.guild._state, '_client', None) or getattr(channel.guild._state, 'client', None)
                        except:
                            pass
                
                # Always use the new singleton API for consistency and reliability
                from managers.leveling import _LevelingManagerCore
                core_manager = _LevelingManagerCore()
                await core_manager.award_xp(
                    user=user,
                    xp=milestone_xp,
                    source="Milestone Reward",
                    game_id=0,  # Use 0 for milestone rewards (not tied to a specific game)
                    channel=channel,
                    bot=client,  # Use the client we found, or None if not available
                    test_mode=False
                )
            except Exception as e:
                milestones_manager.logger.error(f"Error awarding milestone XP: {e}")
                import traceback
                milestones_manager.logger.error(traceback.format_exc())
            
            # Resolve emoji to full Discord format
            emoji_str = achievement.get('emoji', '🏅')
            resolved_emoji = milestones_manager._resolve_emoji(emoji_str, guild) if guild else emoji_str
            
            if channel:
                try:
                    await channel.send(
                        f"🏆 **Achievement Unlocked!** {user.mention} earned: **{achievement.get('name', 'Unknown')}** {resolved_emoji} (+{milestone_xp} XP)"
                    )
                except Exception as e:
                    # If channel send fails, try DM
                    try:
                        dm_channel = await user.create_dm()
                        await dm_channel.send(
                            f"🏆 **Achievement Unlocked!** You earned: **{achievement.get('name', 'Unknown')}** {resolved_emoji} (+{milestone_xp} XP)"
                        )
                    except:
                        pass
    
    return new_achievements


async def check_dm_game_win(user: discord.User, game_type: str, channel: discord.TextChannel = None, bot = None):
    """Check achievements after a DM game win"""
    db = await DatabasePool.get_instance()
    user_id_str = str(user.id)
    
    # Get current win count
    if game_type == "TicTacToe":
        result = await db.execute(
            "SELECT COUNT(*) as count FROM users_tictactoe WHERE user_id = %s AND won = 'Won'",
            (user_id_str,)
        )
    elif game_type == "Wordle":
        result = await db.execute(
            "SELECT COUNT(*) as count FROM users_wordle WHERE user_id = %s AND won = 'Won'",
            (user_id_str,)
        )
    elif game_type == "Connect Four":
        result = await db.execute(
            "SELECT COUNT(*) as count FROM users_connectfour WHERE user_id = %s AND status = 'Won'",
            (user_id_str,)
        )
    elif game_type == "Memory":
        result = await db.execute(
            "SELECT COUNT(*) as count FROM users_memory WHERE user_id = %s AND won = 'Won'",
            (user_id_str,)
        )
    elif game_type == "2048":
        result = await db.execute(
            "SELECT COUNT(*) as count FROM users_2048 WHERE user_id = %s AND status = 'Won'",
            (user_id_str,)
        )
    elif game_type == "Minesweeper":
        result = await db.execute(
            "SELECT COUNT(*) as count FROM users_minesweeper WHERE user_id = %s AND won = 'Won'",
            (user_id_str,)
        )
    elif game_type == "Hangman":
        result = await db.execute(
            "SELECT COUNT(*) as count FROM users_hangman WHERE user_id = %s AND won = 'Won'",
            (user_id_str,)
        )
    else:
        return []
    
    win_count = result[0]['count'] if result else 0
    return await check_game_achievements(user, game_type, "wins", win_count, channel, bot)


async def check_chat_game_play(user: discord.User, game_type: str, channel: discord.TextChannel = None, bot = None):
    """Check achievements after playing a chat game"""
    db = await DatabasePool.get_instance()
    user_id_str = str(user.id)
    
    # Get current game count
    result = await db.execute(
        "SELECT COUNT(*) as count FROM xp_logs WHERE user_id = %s AND source = %s",
        (user_id_str, game_type)
    )
    
    game_count = result[0]['count'] if result else 0
    return await check_game_achievements(user, game_type, "total_games", game_count, channel, bot)


async def check_level_achievement(user: discord.User, level: int, channel: discord.TextChannel = None, bot = None):
    """Check achievements for level milestones"""
    return await check_game_achievements(user, "Global", "level", level, channel, bot)


async def check_xp_achievement(user: discord.User, total_xp: int, channel: discord.TextChannel = None, bot = None):
    """Check achievements for total XP milestones"""
    # Query the database to get the actual total XP from all sources
    # This ensures we're checking against the real total, not just the passed value
    try:
        db = await DatabasePool.get_instance()
        result = await db.execute(
            "SELECT SUM(xp) as total FROM xp_logs WHERE user_id = %s",
            (str(user.id),)
        )
        actual_total_xp = int(result[0]['total'] or 0) if result else 0
        # Use the actual total from database, but fallback to passed value if query fails
        total_xp = actual_total_xp if actual_total_xp > 0 else total_xp
    except Exception as e:
        # If query fails, use the passed value as fallback
        pass
    
    return await check_game_achievements(user, "Global", "total_xp_all", total_xp, channel, bot)

