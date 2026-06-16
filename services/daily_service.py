"""Daily reward claim logic shared by /daily and the #Leveling button."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import discord

from core.config.manager import ConfigManager
from core.database.pool import DatabasePool

MAX_DAILY_XP = 300


@dataclass
class DailyClaimResult:
    embed: discord.Embed
    ephemeral: bool


def _build_embed(
    bot: discord.Client,
    *,
    title: str,
    description: str,
    fields: list[tuple[str, str, bool]] | None = None,
) -> discord.Embed:
    config = ConfigManager.get_instance()
    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.from_str(config.get("config", "EMBED_COLOR")),
    )
    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)
    logo_url = bot.app.embeds.get_logo_url(config.get("config", "LOGO"))
    embed.set_footer(text=config.get("config", "FOOTER"), icon_url=logo_url)
    return embed


async def claim_daily(
    bot: discord.Client,
    user: discord.User | discord.Member,
    channel: discord.abc.Messageable,
) -> DailyClaimResult:
    db = await DatabasePool.get_instance()
    user_id = str(user.id)
    current_time = int(datetime.now(timezone.utc).timestamp())

    daily_data = await db.execute(
        "SELECT * FROM daily_claims WHERE user_id = %s",
        (user_id,),
    )

    if not daily_data:
        streak = 1
        xp = 10
        await db.execute_insert(
            "INSERT INTO daily_claims (user_id, last_claimed, streak) VALUES (%s, %s, %s)",
            (user_id, current_time, streak),
        )
    else:
        last_claimed = int(daily_data[0]["last_claimed"])
        current_streak = int(daily_data[0]["streak"])

        last_claimed_date = datetime.fromtimestamp(last_claimed, tz=timezone.utc).date()
        current_date = datetime.fromtimestamp(current_time, tz=timezone.utc).date()

        if last_claimed_date == current_date:
            next_claim_time = datetime.fromtimestamp(last_claimed, tz=timezone.utc) + timedelta(
                days=1
            )
            next_claim_timestamp = int(
                next_claim_time.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
            )
            embed = _build_embed(
                bot,
                title="⏰ Daily Reward Already Claimed",
                description=(
                    f"You've already claimed your daily reward today!\n\n"
                    f"**Current Streak:** {current_streak} days 🔥\n"
                    f"**Next Claim:** <t:{next_claim_timestamp}:R>"
                ),
            )
            return DailyClaimResult(embed=embed, ephemeral=True)

        yesterday = current_date - timedelta(days=1)
        streak = current_streak + 1 if last_claimed_date == yesterday else 1
        xp = min(10 + (streak - 1) * 5, MAX_DAILY_XP)

        await db.execute(
            "UPDATE daily_claims SET last_claimed = %s, streak = %s WHERE user_id = %s",
            (current_time, streak, user_id),
        )

    from managers.leveling import LevelingManager

    lvl_mng = LevelingManager(
        user=user,
        channel=channel,
        client=bot,
        xp=xp,
        source="Daily Reward",
        game_id=0,
    )
    await lvl_mng.update()

    await bot.app.achievements.check_game_achievements(
        user,
        "Daily",
        "streak",
        streak,
        channel,
        bot,
    )

    fields = None
    if streak >= 7:
        fields = [
            (
                "🔥 Streak Bonus!",
                f"You've maintained a {streak}-day streak! Keep it up!",
                False,
            )
        ]

    embed = _build_embed(
        bot,
        title="🎁 Daily Reward Claimed!",
        description=(
            f"You've claimed your daily reward!\n\n"
            f"**XP Earned:** {xp} XP\n"
            f"**Current Streak:** {streak} day{'s' if streak != 1 else ''} 🔥\n"
            f"**Next Reward:** {min(xp + 5, MAX_DAILY_XP)} XP (if you maintain your streak)"
        ),
        fields=fields,
    )
    return DailyClaimResult(embed=embed, ephemeral=False)


async def get_daily_streak(user_id: int) -> dict:
    db = await DatabasePool.get_instance()
    daily_data = await db.execute(
        "SELECT streak, last_claimed FROM daily_claims WHERE user_id = %s",
        (str(user_id),),
    )

    if not daily_data:
        return {"streak": 0, "last_claimed": None}

    return {
        "streak": int(daily_data[0]["streak"]),
        "last_claimed": int(daily_data[0]["last_claimed"]),
    }
