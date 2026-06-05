"""Local HTTP API for dashboard games admin."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from typing import TYPE_CHECKING

import discord
from aiohttp import web

if TYPE_CHECKING:
    from bot import MinecadiaBot

log = logging.getLogger("dashboard_http")
_server: web.AppRunner | None = None


def _api_secret() -> str | None:
    return os.environ.get("GAMES_BOT_API_SECRET") or os.environ.get(
        "CONTROL_API_SECRET"
    )


def _api_port() -> int:
    return int(os.environ.get("GAMES_BOT_API_PORT", "8789"))


def _auth(request: web.Request) -> bool:
    secret = _api_secret()
    return bool(secret and request.headers.get("X-Games-Key") == secret)


async def start_dashboard_http(bot: "MinecadiaBot") -> None:
    global _server
    secret = _api_secret()
    if not secret:
        log.warning(
            "GAMES_BOT_API_SECRET / CONTROL_API_SECRET not set — dashboard games API disabled"
        )
        return

    async def status(_request: web.Request) -> web.Response:
        gm = bot.game_manager
        return web.json_response(
            {
                "chatGamesRunning": bool(gm and gm.chat_game_running),
                "dmGamesRunning": bool(gm and gm.dm_game_running),
            }
        )

    async def toggle_chat(_request: web.Request) -> web.Response:
        gm = bot.game_manager
        if not gm:
            return web.json_response({"error": "Game manager not ready"}, status=503)
        if gm.chat_game_running:
            gm.stop_chat_games()
        else:
            gm.start_chat_games()
        return web.json_response({"running": gm.chat_game_running})

    async def toggle_dm(_request: web.Request) -> web.Response:
        gm = bot.game_manager
        if not gm:
            return web.json_response({"error": "Game manager not ready"}, status=503)
        if gm.dm_game_running:
            gm.stop_dm_games()
        else:
            gm.start_dm_games()
        return web.json_response({"running": gm.dm_game_running})

    async def force_chat(request: web.Request) -> web.Response:
        body = await request.json()
        game = str(body.get("game", "")).lower()
        channel_id = body.get("channel_id")

        from games.chat.unscramble import Unscramble
        from games.chat.flag_guesser import FlagGuesser
        from games.chat.math_quiz import MathQuiz
        from games.chat.trivia import Trivia
        from games.chat.emoji_quiz import EmojiQuiz
        from games.chat.guess_the_number import GuessTheNumber

        game_map = {
            "unscramble": Unscramble,
            "flag_guesser": FlagGuesser,
            "math_quiz": MathQuiz,
            "trivia": Trivia,
            "emoji_quiz": EmojiQuiz,
            "guess_the_number": GuessTheNumber,
        }
        game_class = game_map.get(game)
        if not game_class:
            return web.json_response({"error": f"Invalid game: {game}"}, status=400)

        channel = None
        if channel_id:
            channel = bot.get_channel(int(channel_id))
        if channel is None:
            from core.config.manager import ConfigManager
            cfg = ConfigManager.get_instance()
            guild_id = int(cfg.get("config", "GUILD_ID") or cfg.get("config", "guild_id") or 0)
            guild = bot.get_guild(guild_id)
            if guild:
                ch_id = cfg.get("config", "GAMES_CHANNEL") or cfg.get(
                    "config", "games_channel"
                )
                if ch_id:
                    channel = guild.get_channel(int(ch_id))

        if not channel or not isinstance(channel, discord.TextChannel):
            return web.json_response({"error": "Channel not found"}, status=404)

        instance = game_class(bot)
        msg = await instance.run(channel)
        if msg:
            return web.json_response({"ok": True})
        return web.json_response({"error": "Failed to start game"}, status=500)

    async def force_dm_refresh(_request: web.Request) -> web.Response:
        gm = bot.game_manager
        if not gm:
            return web.json_response({"error": "Game manager not ready"}, status=503)
        name = await gm.force_cycle_dm_game()
        if name:
            return web.json_response({"ok": True, "game": name})
        return web.json_response({"error": "Failed to refresh DM game"}, status=500)

    async def add_trivia(request: web.Request) -> web.Response:
        body = await request.json()
        channel_id = str(body.get("channel_id", ""))
        question = str(body.get("question", "")).strip()
        answer = str(body.get("answer", "")).strip()
        if not channel_id or not question or not answer:
            return web.json_response(
                {"error": "channel_id, question, answer required"}, status=400
            )

        trivia_path = (
            Path(__file__).resolve().parent.parent
            / "configs"
            / "games"
            / "trivia.json"
        )
        data = {}
        if trivia_path.exists():
            data = json.loads(trivia_path.read_text(encoding="utf-8"))
        channel_key = channel_id
        if channel_key not in data:
            data[channel_key] = []
        data[channel_key].append({"question": question, "answer": answer})
        trivia_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        from core.config.manager import ConfigManager
        ConfigManager.get_instance().reload_all()
        return web.json_response({"ok": True})

    async def reload_config(_request: web.Request) -> web.Response:
        from core.config.manager import ConfigManager
        ConfigManager.get_instance().reload_all()
        return web.json_response({"ok": True})

    async def wipe_levels(request: web.Request) -> web.Response:
        body = await request.json()
        month = str(body.get("month", "")).strip()
        if not month:
            return web.json_response({"error": "month required"}, status=400)

        cog = bot.get_cog("WipeLevels")
        if cog is None:
            return web.json_response({"error": "WipeLevels cog not loaded"}, status=503)

        from core.config.manager import ConfigManager
        cfg = ConfigManager.get_instance()
        guild_id = int(cfg.get("config", "GUILD_ID") or 0)
        guild = bot.get_guild(guild_id)
        if guild is None:
            return web.json_response({"error": "Guild not available"}, status=503)

        actor_id = int(body.get("actor_id") or bot.owner_id or 0)
        actor = guild.get_member(actor_id)
        if actor is None:
            try:
                actor = await guild.fetch_member(actor_id)
            except Exception:
                actor = guild.me

        try:
            result = await cog.dashboard_wipe(guild, month, actor)
            return web.json_response({"ok": True, "message": result})
        except Exception as exc:
            log.exception("Dashboard wipe failed")
            from core.errors.messages import user_message_for

            return web.json_response({"error": user_message_for(exc)}, status=500)

    app = web.Application()

    def wrap(handler):
        async def inner(request: web.Request) -> web.Response:
            if not _auth(request):
                return web.json_response({"error": "Unauthorized"}, status=401)
            return await handler(request)

        return inner

    async def health(_request: web.Request) -> web.Response:
        return web.json_response({"ok": True})

    app.router.add_get("/status", wrap(status))
    app.router.add_get("/health", health)
    app.router.add_post("/toggle-chat-games", wrap(toggle_chat))
    app.router.add_post("/toggle-dm-games", wrap(toggle_dm))
    app.router.add_post("/force-chat-game", wrap(force_chat))
    app.router.add_post("/force-dm-refresh", wrap(force_dm_refresh))
    app.router.add_post("/add-trivia", wrap(add_trivia))
    app.router.add_post("/reload-config", wrap(reload_config))
    app.router.add_post("/wipe-levels", wrap(wipe_levels))

    from assets.http.session_http import (
        handle_session_live,
        handle_session_chat_action,
        handle_active_sessions,
    )

    async def session_live(request: web.Request) -> web.Response:
        return await handle_session_live(request, bot)

    async def session_chat_action(request: web.Request) -> web.Response:
        return await handle_session_chat_action(request, bot)

    async def active_sessions(_request: web.Request) -> web.Response:
        return await handle_active_sessions(_request, bot)

    app.router.add_get("/session/{game_id}", wrap(session_live))
    app.router.add_get("/sessions/active", wrap(active_sessions))
    app.router.add_post("/session/chat-action", wrap(session_chat_action))

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", _api_port())
    await site.start()
    _server = runner
    log.info("Dashboard HTTP listening on 127.0.0.1:%s", _api_port())


async def stop_dashboard_http() -> None:
    global _server
    if _server is not None:
        await _server.cleanup()
        _server = None
