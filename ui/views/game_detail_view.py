from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

import discord

from core.config.manager import ConfigManager
from core.database.pool import DatabasePool
from core.logging.setup import get_logger
from repositories.game_session_repository import normalize_game_type


async def build_game_detail_payload(bot, config: ConfigManager, game_id: int) -> Optional[Dict[str, Any]]:
    db = await DatabasePool.get_instance()

    game_info = await db.execute(
        "SELECT name AS game_name, refreshed_at, is_dm AS dm_game FROM games WHERE id = %s",
        (game_id,),
    )
    if not game_info:
        return None

    game = game_info[0]
    game_name = game["game_name"]
    is_dm_game = bool(game.get("dm_game", False))

    refreshed_at = game["refreshed_at"]
    if isinstance(refreshed_at, str):
        refreshed_at = int(refreshed_at)

    embed = discord.Embed(
        title=f"🎮 Game #{game_id} - {game_name}",
        color=discord.Color.from_str(config.get("config", "EMBED_COLOR")),
        timestamp=datetime.fromtimestamp(refreshed_at, tz=timezone.utc) if refreshed_at else None,
    )

    embed.add_field(
        name="Game Info",
        value=(
            f"**Type:** {'DM Game' if is_dm_game else 'Chat Game'}\n"
            f"**Created:** <t:{game['refreshed_at']}:F>\n"
            f"**Created:** <t:{game['refreshed_at']}:R>"
        ),
        inline=False,
    )

    xp_logs = await db.execute(
        """
        SELECT user_id, xp, source, COALESCE(xl.timestamp, g.refreshed_at) as timestamp
        FROM xp_logs xl
        LEFT JOIN games g ON xl.game_id = g.id
        WHERE xl.game_id = %s
        ORDER BY COALESCE(xl.timestamp, g.refreshed_at) DESC
        LIMIT 500
        """,
        (game_id,),
    )

    if xp_logs:
        total_xp = sum(log["xp"] for log in xp_logs)
        unique_users = len(set(log["user_id"] for log in xp_logs))

        embed.add_field(
            name="XP Statistics",
            value=(
                f"**Total XP Awarded:** {total_xp:,}\n"
                f"**Unique Players:** {unique_users}\n"
                f"**Total Awards:** {len(xp_logs)}"
            ),
            inline=False,
        )

        user_xp: Dict[int, int] = {}
        for log in xp_logs:
            user_id = int(log["user_id"])
            user_xp[user_id] = user_xp.get(user_id, 0) + log["xp"]

        top_players = sorted(user_xp.items(), key=lambda item: item[1], reverse=True)[:10]
        top_players_text = "\n".join(
            [f"{index + 1}. <@{user_id}> - {xp:,} XP" for index, (user_id, xp) in enumerate(top_players)]
        )

        embed.add_field(
            name="Top Players",
            value=top_players_text or "No players",
            inline=False,
        )

    game_data: List[Dict[str, Any]] = []
    if is_dm_game:
        try:
            rows = await db.execute(
                """
                SELECT user_id, status, stats, started_at, ended_at
                FROM game_sessions
                WHERE game_id = %s
                ORDER BY started_at DESC
                LIMIT 50
                """,
                (game_id,),
            )

            for row in rows:
                user_id = int(row["user_id"])
                user = bot.get_user(user_id)
                if user is None:
                    try:
                        user = await bot.fetch_user(user_id)
                    except Exception:
                        user = None

                display_name = None
                if user is not None:
                    display_name = getattr(user, "display_name", None) or getattr(user, "global_name", None) or getattr(user, "name", None)

                stats = row.get("stats")
                if isinstance(stats, str):
                    import json

                    stats = json.loads(stats) if stats else {}
                elif not stats:
                    stats = {}

                game_data.append(
                    {
                        "user_id": user_id,
                        "display_name": display_name or str(user_id),
                        "status": row["status"],
                        "score": stats.get("score") or stats.get("player_cells"),
                        "started_at": row["started_at"],
                        "ended_at": row.get("ended_at"),
                        "moves": (
                            stats.get("moves")
                            or stats.get("attempts")
                            or stats.get("turns")
                            or stats.get("cells_revealed")
                        ),
                    }
                )

            if game_data:
                status_counts: Dict[str, int] = {}
                for row in game_data:
                    status = row.get("status", "unknown")
                    status_counts[status] = status_counts.get(status, 0) + 1

                status_text = "\n".join(
                    [f"**{status}:** {count}" for status, count in status_counts.items()]
                )

                embed.add_field(
                    name="Game Statuses",
                    value=status_text or "No data",
                    inline=True,
                )

        except Exception as exc:
            logger = get_logger("Commands")
            logger.error(f"Error fetching game session data for game {game_id}: {exc}")

    logo_url = bot.app.embeds.get_logo_url(config.get("config", "LOGO"))
    embed.set_footer(text=config.get("config", "FOOTER"), icon_url=logo_url)

    return {
        "embed": embed,
        "game_id": game_id,
        "game_name": game_name,
        "is_dm_game": is_dm_game,
        "game_data": game_data,
    }


class GameDetailRemovePlayerSelect(discord.ui.Select):
    def __init__(self, parent_view: "GameDetailView", options: List[discord.SelectOption]):
        self.parent_view = parent_view
        super().__init__(
            placeholder="Remove a player from this game...",
            options=options,
            custom_id="game_detail_remove_player_select",
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.parent_view.remove_player(interaction, int(self.values[0]))


class GameDetailView(discord.ui.View):
    def __init__(
        self,
        bot,
        config: ConfigManager,
        game_id: int,
        game_name: str,
        is_dm_game: bool,
        game_data: Optional[List[Dict[str, Any]]] = None,
    ):
        super().__init__(timeout=None)
        self.bot = bot
        self.config = config
        self.game_id = game_id
        self.game_name = game_name
        self.is_dm_game = is_dm_game
        self.game_data = game_data or []
        self.logger = get_logger("Commands")

        if self.is_dm_game and self.game_data:
            options = []
            for row in self.game_data[:25]:
                user_id = int(row.get("user_id", 0))
                display_name = row.get("display_name") or str(user_id)
                status = row.get("status", "unknown")
                options.append(
                    discord.SelectOption(
                        label=f"{display_name} - {status}",
                        value=str(user_id),
                        description=f"Remove from Game #{self.game_id}",
                    )
                )

            if options:
                self.add_item(GameDetailRemovePlayerSelect(self, options))

    async def remove_player(self, interaction: discord.Interaction, user_id: int):
        if not self.is_dm_game:
            await interaction.followup.send(
                "`❌` Player removal is only available for DM games.",
                ephemeral=True,
            )
            return

        game_type = normalize_game_type(self.game_name)
        db = await DatabasePool.get_instance()

        try:
            async with db.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        "DELETE FROM xp_logs WHERE game_id = %s AND user_id = %s",
                        (self.game_id, user_id),
                    )
                    xp_removed = cursor.rowcount

                    await cursor.execute(
                        "DELETE FROM game_sessions WHERE game_id = %s AND user_id = %s AND game_type = %s",
                        (self.game_id, user_id, game_type),
                    )
                    sessions_removed = cursor.rowcount
        except Exception as exc:
            self.logger.error(f"Failed removing player {user_id} from game {self.game_id}: {exc}")
            await interaction.followup.send(
                f"`❌` Failed to remove <@{user_id}> from Game #{self.game_id}.",
                ephemeral=True,
            )
            return

        if not xp_removed and not sessions_removed:
            await interaction.followup.send(
                f"`❌` No session found for <@{user_id}> in Game #{self.game_id}.",
                ephemeral=True,
            )
            return

        payload = await build_game_detail_payload(self.bot, self.config, self.game_id)
        if not payload:
            await interaction.followup.send(
                f"`✅` Removed <@{user_id}> from Game #{self.game_id}.",
                ephemeral=True,
            )
            return

        refreshed_view = GameDetailView(
            self.bot,
            self.config,
            self.game_id,
            payload["game_name"],
            payload["is_dm_game"],
            payload["game_data"],
        )

        if interaction.message:
            await interaction.message.edit(embed=payload["embed"], view=refreshed_view)

        await interaction.followup.send(
            f"`✅` Removed <@{user_id}> from Game #{self.game_id}.",
            ephemeral=True,
        )