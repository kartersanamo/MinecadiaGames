import discord

from core.config.manager import ConfigManager
from core.database.pool import DatabasePool
from managers.milestones import MilestonesManager

GAMES_CHANNEL_ID = 1456658225964388504


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
    async def _announce_achievement_unlock(
        cls,
        user: discord.User,
        achievement: dict,
        milestone_xp: int,
        resolved_emoji: str,
        channel: discord.abc.Messageable | None,
        bot,
    ) -> None:
        name = achievement.get("name", "Unknown")
        public_message = (
            f"🏆 **Achievement Unlocked!** {user.mention} earned: "
            f"**{name}** {resolved_emoji} (+{milestone_xp} XP)"
        )
        dm_message = (
            f"🏆 **Achievement Unlocked!** You earned: "
            f"**{name}** {resolved_emoji} (+{milestone_xp} XP)"
        )

        config = ConfigManager.get_instance()
        leveling_channel_id = config.get("config", "LEVELING_CHANNEL")
        trigger_id = getattr(channel, "id", None) if channel else None

        if trigger_id == leveling_channel_id:
            try:
                dm_ch = await user.create_dm()
                await dm_ch.send(dm_message)
            except (discord.Forbidden, discord.HTTPException):
                games_ch = bot.get_channel(GAMES_CHANNEL_ID) if bot else None
                if games_ch:
                    try:
                        await games_ch.send(public_message)
                    except Exception:
                        pass
            return

        if channel:
            try:
                await channel.send(public_message)
                return
            except (discord.Forbidden, discord.HTTPException):
                pass

        try:
            dm_ch = await user.create_dm()
            await dm_ch.send(dm_message)
        except Exception:
            pass

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

                await cls._announce_achievement_unlock(
                    user, achievement, milestone_xp, resolved_emoji, channel, bot
                )

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

        from repositories.game_session_repository import normalize_game_type

        game_type_key = normalize_game_type(game_type)
        result = await db.execute(
            """SELECT COUNT(*) AS count FROM game_sessions
               WHERE user_id = %s AND game_type = %s AND status = 'won'""",
            (user.id, game_type_key),
        )
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
