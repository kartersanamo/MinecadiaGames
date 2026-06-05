import discord

from core.database.pool import DatabasePool
from managers.milestones import MilestonesManager


class AchievementService:
    @staticmethod
    def _calculate_milestone_xp(milestone: dict, all_milestones: list) -> int:
        sorted_milestones = sorted(all_milestones, key=lambda x: x.get("threshold", 0))
        try:
            milestone_index = next(
                i
                for i, m in enumerate(sorted_milestones)
                if m.get("id") == milestone.get("id")
            )
        except StopIteration:
            milestone_index = 0

        total_milestones = len(sorted_milestones)
        if total_milestones == 1:
            xp = 550
        else:
            base_xp = 400
            max_xp = 700
            xp_range = max_xp - base_xp
            if total_milestones > 1:
                progress = milestone_index / (total_milestones - 1)
                xp = int(base_xp + (xp_range * progress))
            else:
                xp = base_xp

        return max(400, min(700, xp))

    @classmethod
    async def check_game_achievements(
        cls,
        user: discord.User,
        game_type: str,
        metric: str,
        value: int,
        channel: discord.TextChannel = None,
        bot=None,
    ):
        milestones_manager = MilestonesManager()
        client = bot
        if not client and channel:
            try:
                if hasattr(channel, "_state"):
                    client = getattr(channel._state, "_client", None) or getattr(
                        channel._state, "client", None
                    )
            except Exception:
                pass
            if not client and hasattr(channel, "guild") and channel.guild:
                try:
                    if hasattr(channel.guild, "_state"):
                        client = getattr(
                            channel.guild._state, "_client", None
                        ) or getattr(channel.guild._state, "client", None)
                except Exception:
                    pass

        new_achievements = await milestones_manager.check_achievements(
            user.id, game_type, metric, value, user=user, channel=channel, client=client
        )

        if new_achievements:
            milestones_config = milestones_manager.milestones_config
            game_milestones = milestones_config.get(game_type, {})
            metric_milestones = game_milestones.get(metric, [])
            guild = channel.guild if channel and hasattr(channel, "guild") else None

            for achievement in new_achievements:
                milestone_xp = cls._calculate_milestone_xp(achievement, metric_milestones)
                emoji_str = achievement.get("emoji", "🏅")
                resolved_emoji = (
                    milestones_manager._resolve_emoji(emoji_str, guild)
                    if guild
                    else emoji_str
                )

                if channel:
                    try:
                        await channel.send(
                            f"🏆 **Achievement Unlocked!** {user.mention} earned: "
                            f"**{achievement.get('name', 'Unknown')}** {resolved_emoji} "
                            f"(+{milestone_xp} XP)"
                        )
                    except Exception:
                        try:
                            dm_channel = await user.create_dm()
                            await dm_channel.send(
                                f"🏆 **Achievement Unlocked!** You earned: "
                                f"**{achievement.get('name', 'Unknown')}** {resolved_emoji} "
                                f"(+{milestone_xp} XP)"
                            )
                        except Exception:
                            pass

        return new_achievements

    @classmethod
    async def check_dm_game_win(
        cls,
        user: discord.User,
        game_type: str,
        channel: discord.TextChannel = None,
        bot=None,
    ):
        db = await DatabasePool.get_instance()
        user_id_str = str(user.id)

        win_queries = {
            "TicTacToe": (
                "SELECT COUNT(*) as count FROM users_tictactoe WHERE user_id = %s AND won = 'Won'",
                (user_id_str,),
            ),
            "Wordle": (
                "SELECT COUNT(*) as count FROM users_wordle WHERE user_id = %s AND won = 'Won'",
                (user_id_str,),
            ),
            "Connect Four": (
                "SELECT COUNT(*) as count FROM users_connectfour WHERE user_id = %s AND status = 'Won'",
                (user_id_str,),
            ),
            "Memory": (
                "SELECT COUNT(*) as count FROM users_memory WHERE user_id = %s AND won = 'Won'",
                (user_id_str,),
            ),
            "2048": (
                "SELECT COUNT(*) as count FROM users_2048 WHERE user_id = %s AND status IN ('Won', 'Cashed Out')",
                (user_id_str,),
            ),
            "Minesweeper": (
                "SELECT COUNT(*) as count FROM users_minesweeper WHERE user_id = %s AND won = 'Won'",
                (user_id_str,),
            ),
            "Hangman": (
                "SELECT COUNT(*) as count FROM users_hangman WHERE user_id = %s AND won = 'Won'",
                (user_id_str,),
            ),
            "Filler": (
                "SELECT COUNT(*) as count FROM users_filler WHERE user_id = %s AND won = 'Won'",
                (user_id_str,),
            ),
        }

        query = win_queries.get(game_type)
        if not query:
            return []

        result = await db.execute(query[0], query[1])
        win_count = result[0]["count"] if result else 0
        return await cls.check_game_achievements(
            user, game_type, "wins", win_count, channel, bot
        )

    @classmethod
    async def check_chat_game_play(
        cls,
        user: discord.User,
        game_type: str,
        channel: discord.TextChannel = None,
        bot=None,
    ):
        db = await DatabasePool.get_instance()
        user_id_str = str(user.id)
        result = await db.execute(
            "SELECT COUNT(*) as count FROM xp_logs WHERE user_id = %s AND source = %s",
            (user_id_str, game_type),
        )
        game_count = result[0]["count"] if result else 0
        return await cls.check_game_achievements(
            user, game_type, "total_games", game_count, channel, bot
        )

    @classmethod
    async def check_level_achievement(
        cls,
        user: discord.User,
        level: int,
        channel: discord.TextChannel = None,
        bot=None,
    ):
        return await cls.check_game_achievements(
            user, "Global", "level", level, channel, bot
        )

    @classmethod
    async def check_xp_achievement(
        cls,
        user: discord.User,
        total_xp: int,
        channel: discord.TextChannel = None,
        bot=None,
    ):
        try:
            db = await DatabasePool.get_instance()
            result = await db.execute(
                "SELECT SUM(xp) as total FROM xp_logs WHERE user_id = %s",
                (str(user.id),),
            )
            actual_total_xp = int(result[0]["total"] or 0) if result else 0
            total_xp = actual_total_xp if actual_total_xp > 0 else total_xp
        except Exception:
            pass

        return await cls.check_game_achievements(
            user, "Global", "total_xp_all", total_xp, channel, bot
        )


_default = AchievementService()
check_game_achievements = _default.check_game_achievements
check_dm_game_win = _default.check_dm_game_win
check_chat_game_play = _default.check_chat_game_play
check_level_achievement = _default.check_level_achievement
check_xp_achievement = _default.check_xp_achievement
