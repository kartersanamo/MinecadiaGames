"""Dashboard HTTP handlers for live chat game session control."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

import discord
from aiohttp import web

from services.chat_game_registry import registry

if TYPE_CHECKING:
    from bot import MinecadiaBot


def _extract_correct_answer(game_type: str | None, original_state: dict) -> str | None:
    """Match in-Discord Manage Chat Game → Show Answer logic."""
    if not original_state:
        return None
    game_type = (game_type or "").lower()
    if game_type in ("trivia", "math_quiz", "flag_guesser", "emoji_quiz"):
        return original_state.get("correct_answer")
    if game_type == "unscramble":
        return original_state.get("word")
    if game_type == "guess_the_number":
        secret = original_state.get("secret_number")
        if secret is not None:
            return f"The number is **{secret}**"
    return original_state.get("correct_answer") or original_state.get("word")


def _serialize_live(message_id: int, game_data: dict, message_url: str | None = None) -> dict:
    view = game_data.get("view")
    winners = []
    if view and hasattr(view, "winners"):
        for w in view.winners:
            uid = getattr(w.get("user"), "id", None) if isinstance(w.get("user"), discord.User) else w.get("user_id")
            winners.append({"user_id": str(uid) if uid else None, "xp": w.get("xp")})
    elif game_data.get("winners"):
        for w in game_data["winners"]:
            uid = getattr(w.get("user"), "id", None) if isinstance(w.get("user"), discord.User) else w.get("user_id")
            winners.append({"user_id": str(uid) if uid else None, "xp": w.get("xp")})

    out = {
        "active": True,
        "messageId": str(message_id),
        "gameType": game_data.get("game_type"),
        "xpMultiplier": game_data.get("xp_multiplier", 1.0),
        "testMode": bool(game_data.get("test_mode")),
        "winners": winners,
        "activityLog": game_data.get("activity_log", []),
    }
    if message_url:
        out["messageUrl"] = message_url
    return out


async def _fetch_message(bot: "MinecadiaBot", message_id: int) -> Optional[discord.Message]:
    for guild in bot.guilds:
        for ch in guild.text_channels:
            try:
                return await ch.fetch_message(message_id)
            except Exception:
                continue
    return None


async def get_session_live(bot: "MinecadiaBot", game_id: int) -> dict:
    message_id, game_data = registry.find_by_game_id(game_id)
    if not message_id or not game_data:
        return {"active": False}

    message_url = None
    msg = await _fetch_message(bot, message_id)
    answer = None
    answer_revealed = False
    if msg:
        message_url = msg.jump_url
        if msg.embeds:
            for field in msg.embeds[0].fields:
                if field.name == "Answer":
                    answer = field.value
                    answer_revealed = True
                    break

    out = _serialize_live(message_id, game_data, message_url)
    game_type = game_data.get("game_type")
    original_state = game_data.get("original_state") or {}
    staff_answer = _extract_correct_answer(game_type, original_state)
    if staff_answer:
        out["staffAnswer"] = str(staff_answer)
    if answer_revealed and answer:
        out["answer"] = answer
        out["answerRevealed"] = True
    return out


async def apply_chat_action(bot: "MinecadiaBot", game_id: int, action: str) -> dict:
    message_id, game_data = registry.find_by_game_id(game_id)
    if not message_id or not game_data:
        return {"error": "No active chat game in registry for this session", "active": False}

    message = await _fetch_message(bot, message_id)
    if message is None:
        return {"error": "Could not fetch Discord message for this game"}

    if action == "toggle_2x":
        current_mult = game_data.get("xp_multiplier", 1.0)
        new_mult = 2.0 if current_mult == 1.0 else 1.0
        registry.update_xp_multiplier(message_id, new_mult)
        view = game_data.get("view")
        if view and hasattr(view, "xp_multiplier"):
            view.xp_multiplier = new_mult
        embed = message.embeds[0] if message.embeds else discord.Embed(title="Game")
        title = embed.title or ""
        title = re.sub(r"\s*\(.*?XP\)", "", title)
        title = re.sub(r"\s*🧪 TEST GAME 🧪", "", title)
        if new_mult == 2.0:
            title += " (DOUBLE XP)"
        elif new_mult > 1.0:
            title += f" ({new_mult:.1f}x XP)"
        if game_data.get("test_mode"):
            title += " 🧪 TEST GAME 🧪"
        embed.title = title
        is_real_view = view and isinstance(view, discord.ui.View)
        if is_real_view:
            await message.edit(embed=embed, view=view)
        else:
            await message.edit(embed=embed)
        registry.log_activity(message_id, 0, "toggle_2x", f"XP multiplier {new_mult}x (dashboard)", True)
        return {"ok": True, "xpMultiplier": new_mult}

    if action == "show_correct_answer":
        game_type = game_data.get("game_type")
        original_state = game_data.get("original_state") or {}
        answer = _extract_correct_answer(game_type, original_state)
        if not answer:
            return {"error": "Answer not available for this game"}

        registry.log_activity(
            message_id,
            0,
            "show_answer",
            f"Viewed via dashboard (not posted to channel): {answer}",
            True,
        )
        return {"ok": True, "answer": str(answer), "revealed": True}

    if action == "end_game":
        view = game_data.get("view")
        is_real_view = view and isinstance(view, discord.ui.View)
        embed = message.embeds[0] if message.embeds else discord.Embed(title="Game")
        embed.description = f"This game ended <t:{int(datetime.now(timezone.utc).timestamp())}:R>"
        if not any(f.name == "Winners" for f in embed.fields):
            if view and hasattr(view, "winners") and view.winners:
                winners_text = "\n".join(f"`+{w['xp']}xp` {w['user']}" for w in view.winners)
            else:
                winners_text = "No winners!"
            embed.add_field(name="Winners", value=winners_text, inline=False)
        if is_real_view:
            await message.edit(embed=embed, view=None)
        else:
            await message.edit(embed=embed)
        registry.unregister_game(message_id)
        registry.log_activity(message_id, 0, "end_game", "Ended via dashboard", True)
        return {"ok": True, "ended": True}

    return {"error": f"Unsupported action: {action}"}


async def handle_session_live(request: web.Request, bot: "MinecadiaBot") -> web.Response:
    try:
        game_id = int(request.match_info["game_id"])
    except (TypeError, ValueError):
        return web.json_response({"error": "Invalid game id"}, status=400)
    data = await get_session_live(bot, game_id)
    return web.json_response(data)


async def handle_active_sessions(_request: web.Request, bot: "MinecadiaBot") -> web.Response:
    from services.chat_game_registry import registry

    _ = bot
    return web.json_response({"gameIds": registry.active_game_ids()})


async def handle_session_chat_action(request: web.Request, bot: "MinecadiaBot") -> web.Response:
    try:
        body = await request.json()
        game_id = int(body.get("game_id"))
        action = str(body.get("action", ""))
    except (TypeError, ValueError):
        return web.json_response({"error": "game_id and action required"}, status=400)
    result = await apply_chat_action(bot, game_id, action)
    status = 200 if result.get("ok") else 400
    return web.json_response(result, status=status)
