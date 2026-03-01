from typing import Dict, List, Optional
from core.database.pool import DatabasePool
from core.config.manager import ConfigManager
from managers.leveling import LevelingManager
from core.logging.setup import get_logger
import discord


def _calculate_milestone_xp(milestone: dict, all_milestones: list) -> int:
    """Calculate XP reward for a milestone based on its tier/position (400-700)."""
    sorted_milestones = sorted(all_milestones, key=lambda x: x.get('threshold', 0))
    try:
        milestone_index = next(i for i, m in enumerate(sorted_milestones) if m.get('id') == milestone.get('id'))
    except StopIteration:
        milestone_index = 0
    total_milestones = len(sorted_milestones)
    if total_milestones == 1:
        return 550
    base_xp, max_xp = 400, 700
    progress = milestone_index / (total_milestones - 1) if total_milestones > 1 else 0
    xp = int(base_xp + (max_xp - base_xp) * progress)
    return max(400, min(700, xp))


class MilestonesManager:
    def __init__(self):
        self.config = ConfigManager.get_instance()
        self.logger = get_logger("Milestones")
        self.milestones_config = self.config.get('milestones', {})

    async def check_achievements(
        self,
        user_id: int,
        game_type: str,
        metric: str,
        value: int,
        user: Optional[discord.User] = None,
        channel: Optional[discord.abc.Messageable] = None,
        client: Optional[discord.Client] = None,
    ):
        """Check if user has earned any new achievements for a given metric.
        When user/channel/client are provided, grants milestone XP via LevelingManager (database)."""
        db = await DatabasePool.get_instance()

        game_milestones = self.milestones_config.get(game_type, {})
        metric_milestones = game_milestones.get(metric, [])

        if not metric_milestones:
            return []

        user_achievements = await db.execute(
            "SELECT achievement_id FROM user_achievements WHERE user_id = %s",
            (str(user_id),)
        )
        earned_ids = {row['achievement_id'] for row in user_achievements}

        new_achievements = []
        for milestone in metric_milestones:
            milestone_id = milestone.get('id')
            threshold = milestone.get('threshold', 0)

            if milestone_id in earned_ids:
                continue

            if value >= threshold:
                await self._award_achievement(db, user_id, milestone_id, milestone)

                # Grant XP via LevelingManager (writes to xp_logs + leveling table)
                if user is not None:
                    xp = milestone.get('xp') if milestone.get('xp') is not None else _calculate_milestone_xp(milestone, metric_milestones)
                    if xp > 0:
                        try:
                            lvl_mng = LevelingManager()
                            await lvl_mng.award_xp(
                                user=user,
                                xp=xp,
                                source=f"Milestone: {milestone_id} {milestone.get('name', '')}",
                                game_id=-1,
                                channel=channel,
                                bot=client,
                                test_mode=False,
                            )
                        except Exception as e:
                            self.logger.error(f"Error awarding milestone XP to user {user_id}: {e}")

                new_achievements.append(milestone)
                earned_ids.add(milestone_id)

        return new_achievements
    
    async def _award_achievement(self, db: DatabasePool, user_id: int, achievement_id: str, milestone: Dict):
        """Award an achievement to a user"""
        from datetime import datetime, timezone
        
        try:
            await db.execute_insert(
                "INSERT INTO user_achievements (user_id, achievement_id, earned_at) VALUES (%s, %s, %s)",
                (str(user_id), achievement_id, int(datetime.now(timezone.utc).timestamp()))
            )
            self.logger.info(f"Awarded achievement {achievement_id} to user {user_id}")
        except Exception as e:
            self.logger.error(f"Error awarding achievement {achievement_id} to user {user_id}: {e}")
    
    async def get_user_achievements(self, user_id: int) -> List[Dict]:
        """Get all achievements earned by a user"""
        db = await DatabasePool.get_instance()
        
        user_achievements = await db.execute(
            "SELECT achievement_id, earned_at FROM user_achievements WHERE user_id = %s ORDER BY earned_at DESC",
            (str(user_id),)
        )
        
        # Map to full milestone data
        achievements = []
        for row in user_achievements:
            achievement_id = row['achievement_id']
            milestone = self._find_milestone_by_id(achievement_id)
            if milestone:
                achievements.append({
                    **milestone,
                    'earned_at': row['earned_at']
                })
        
        return achievements
    
    async def get_user_badges(self, user_id: int) -> List[Dict]:
        """Get all badges (highest tier achievements) for a user"""
        achievements = await self.get_user_achievements(user_id)
        
        # Group by game_type and metric, keeping only highest tier
        badge_map = {}
        for achievement in achievements:
            game_type = achievement.get('game_type', '')
            metric = achievement.get('metric', '')
            key = f"{game_type}:{metric}"
            threshold = achievement.get('threshold', 0)
            
            if key not in badge_map or threshold > badge_map[key].get('threshold', 0):
                badge_map[key] = achievement
        
        return list(badge_map.values())
    
    async def get_selected_badge(self, user_id: int) -> Optional[str]:
        """Get the user's selected badge achievement ID"""
        db = await DatabasePool.get_instance()
        result = await db.execute(
            "SELECT selected_badge_id FROM user_badge_preferences WHERE user_id = %s",
            (str(user_id),)
        )
        if result:
            return result[0].get('selected_badge_id')
        return None
    
    async def set_selected_badge(self, user_id: int, achievement_id: Optional[str]):
        """Set the user's selected badge"""
        db = await DatabasePool.get_instance()
        try:
            # Use INSERT ... ON DUPLICATE KEY UPDATE
            await db.execute(
                "INSERT INTO user_badge_preferences (user_id, selected_badge_id) VALUES (%s, %s) "
                "ON DUPLICATE KEY UPDATE selected_badge_id = %s",
                (str(user_id), achievement_id, achievement_id)
            )
        except Exception as e:
            # Table might not exist
            self.logger.warning(f"Error setting badge preference: {e}. Table may need to be created.")
            raise
    
    def _resolve_emoji(self, emoji_str: str, guild: Optional[discord.Guild] = None) -> str:
        """Resolve emoji name to full Discord format with ID"""
        if not emoji_str:
            return ""
        
        # If already in full format (<:name:id>), return as is
        if emoji_str.startswith('<') and emoji_str.endswith('>'):
            return emoji_str
        
        # Extract emoji name from :name: format (remove leading and trailing colons)
        emoji_name = emoji_str.strip(':')
        
        # Try to find emoji in guild
        if guild:
            emoji = discord.utils.get(guild.emojis, name=emoji_name)
            if emoji:
                return str(emoji)  # Returns <:name:id> format
        
        # Fallback: return original if not found (might be a Unicode emoji)
        # If it was in :name: format and not found, return as is (Discord will show it as text)
        return emoji_str
    
    async def get_display_badge(self, user_id: int, guild: Optional[discord.Guild] = None) -> Optional[str]:
        """Get the primary badge emoji to display next to username"""
        # First check if user has a selected badge
        selected_badge_id = await self.get_selected_badge(user_id)
        if selected_badge_id:
            milestone = self._find_milestone_by_id(selected_badge_id)
            if milestone:
                # Verify user has earned this achievement
                db = await DatabasePool.get_instance()
                result = await db.execute(
                    "SELECT achievement_id FROM user_achievements WHERE user_id = %s AND achievement_id = %s",
                    (str(user_id), selected_badge_id)
                )
                if result:
                    emoji_str = milestone.get('emoji')
                    return self._resolve_emoji(emoji_str, guild) if emoji_str else None
        
        # Fallback to highest priority badge
        badges = await self.get_user_badges(user_id)
        
        if not badges:
            return None
        
        # Sort by priority/rarity (highest threshold first, then by game type)
        badges.sort(key=lambda x: (x.get('threshold', 0), x.get('game_type', '')), reverse=True)
        
        # Return emoji of the highest priority badge
        emoji_str = badges[0].get('emoji')
        return self._resolve_emoji(emoji_str, guild) if emoji_str else None
    
    def _find_milestone_by_id(self, achievement_id: str) -> Optional[Dict]:
        """Find a milestone configuration by its ID"""
        for game_type, metrics in self.milestones_config.items():
            # Skip non-dict values (like _comment)
            if not isinstance(metrics, dict):
                continue
            for metric, milestones in metrics.items():
                # Skip non-list values
                if not isinstance(milestones, list):
                    continue
                for milestone in milestones:
                    if isinstance(milestone, dict) and milestone.get('id') == achievement_id:
                        milestone['game_type'] = game_type
                        milestone['metric'] = metric
                        return milestone
        return None
    
    async def get_milestone_progress(self, user_id: int, game_type: str, metric: str) -> Dict:
        """Get user's progress towards all milestones for a metric"""
        db = await DatabasePool.get_instance()
        
        # Get current value for the metric
        current_value = await self._get_current_metric_value(db, user_id, game_type, metric)
        
        # Get all milestones for this metric
        game_milestones = self.milestones_config.get(game_type, {})
        metric_milestones = game_milestones.get(metric, [])
        
        # Get earned achievements
        user_achievements = await db.execute(
            "SELECT achievement_id FROM user_achievements WHERE user_id = %s",
            (str(user_id),)
        )
        earned_ids = {row['achievement_id'] for row in user_achievements}
        
        # Build progress list
        progress = []
        for milestone in sorted(metric_milestones, key=lambda x: x.get('threshold', 0)):
            threshold = milestone.get('threshold', 0)
            is_earned = milestone.get('id') in earned_ids
            progress.append({
                **milestone,
                'threshold': threshold,
                'current': current_value,
                'progress': min(100, (current_value / threshold * 100) if threshold > 0 else 0),
                'earned': is_earned
            })
        
        return {
            'current_value': current_value,
            'milestones': progress
        }
    
    async def _get_current_metric_value(self, db: DatabasePool, user_id: int, game_type: str, metric: str) -> int:
        """Get the current value for a specific metric"""
        user_id_str = str(user_id)
        
        if metric == "wins":
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
            else:
                return 0
            return result[0]['count'] if result else 0
        
        elif metric == "total_games":
            if game_type in ["TicTacToe", "Wordle", "Connect Four", "Memory", "2048", "Minesweeper"]:
                table_name = f"users_{game_type.lower().replace(' ', '')}"
                result = await db.execute(
                    f"SELECT COUNT(*) as count FROM {table_name} WHERE user_id = %s",
                    (user_id_str,)
                )
            else:
                # Chat games - use xp_logs
                result = await db.execute(
                    "SELECT COUNT(*) as count FROM xp_logs WHERE user_id = %s AND source = %s",
                    (user_id_str, game_type)
                )
            return result[0]['count'] if result else 0
        
        elif metric == "total_xp":
            result = await db.execute(
                "SELECT SUM(xp) as total FROM xp_logs WHERE user_id = %s AND source = %s",
                (user_id_str, game_type)
            )
            return int(result[0]['total'] or 0) if result else 0
        
        elif metric == "best_score":
            if game_type == "2048":
                result = await db.execute(
                    "SELECT MAX(score) as max_score FROM users_2048 WHERE user_id = %s",
                    (user_id_str,)
                )
                return int(result[0]['max_score'] or 0) if result else 0
            return 0
        
        elif metric == "level":
            result = await db.execute(
                "SELECT level FROM leveling WHERE user_id = %s",
                (user_id_str,)
            )
            return int(result[0]['level'] or 0) if result else 0
        
        elif metric == "total_xp_all":
            result = await db.execute(
                "SELECT SUM(xp) as total FROM xp_logs WHERE user_id = %s",
                (user_id_str,)
            )
            return int(result[0]['total'] or 0) if result else 0
        
        return 0

