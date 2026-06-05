from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.config.manager import ConfigManager
from core.logging.setup import get_logger
from ui.views.chat_game_admin_view import ChatGameAdminView
from services.chat_game_registry import registry


def _check_admin(interaction: discord.Interaction) -> bool:
    if not interaction.guild:
        return False

    config = ConfigManager.get_instance()
    admin_roles = config.get("config", "ADMIN_ROLES", [])
    user_roles = [role.name for role in interaction.user.roles]

    if "*" in admin_roles:
        return True

    return any(role in admin_roles for role in user_roles)


@app_commands.context_menu(name="Manage Chat Game")
async def manage_chat_game(interaction: discord.Interaction, message: discord.Message):
    """Context menu to manage chat games"""
    if not _check_admin(interaction):
        await interaction.response.send_message(
            "`❌` You don't have permission to use this.", ephemeral=True
        )
        return

    if not message.embeds:
        await interaction.response.send_message(
            "`❌` This message doesn't appear to be a chat game.", ephemeral=True
        )
        return

    embed = message.embeds[0]
    title = embed.title or ""

    game_type = None
    if "Trivia Question" in title:
        game_type = "trivia"
    elif "Math Quiz" in title:
        game_type = "math_quiz"
    elif "Flag Guesser" in title:
        game_type = "flag_guesser"
    elif "Unscramble" in title:
        game_type = "unscramble"
    elif "Emoji Quiz" in title:
        game_type = "emoji_quiz"
    elif "Guess The Number" in title:
        game_type = "guess_the_number"

    if not game_type:
        await interaction.response.send_message(
            "`❌` This doesn't appear to be a chat game message.", ephemeral=True
        )
        return

    game_data = registry.get_game(message.id)
    game_ended = game_data is None
    if game_ended:
        game_data = {
            "game_type": game_type,
            "game_id": 0,
            "view": None,
            "original_state": {},
            "xp_multiplier": 1.0,
            "test_mode": False,
            "ended": True,
        }
        for field in embed.fields:
            if field.name == "Answer":
                answer = field.value
                if game_type == "unscramble":
                    game_data["original_state"] = {"word": answer}
                elif game_type == "guess_the_number":
                    game_data["original_state"] = {"secret_number": answer}
                else:
                    game_data["original_state"] = {"correct_answer": answer}
                break

    bot = interaction.client
    config = ConfigManager.get_instance()
    view = ChatGameAdminView(
        message, game_type, game_data, bot, config, game_ended=game_ended
    )

    game_name_map = {
        "trivia": "Trivia",
        "math_quiz": "Math Quiz",
        "flag_guesser": "Flag Guesser",
        "unscramble": "Unscramble",
        "emoji_quiz": "Emoji Quiz",
        "guess_the_number": "Guess The Number",
    }
    game_name = game_name_map.get(game_type, game_type.title())

    xp_mult = game_data.get("xp_multiplier", 1.0) if game_data else 1.0
    test_mode = game_data.get("test_mode", False) if game_data else False
    winners_count = 0
    if game_data:
        view_obj = game_data.get("view")
        if view_obj and hasattr(view_obj, "winners"):
            winners_count = len(view_obj.winners)
        elif game_data.get("winners"):
            winners_count = len(game_data.get("winners", []))

        if game_ended:
            for field in embed.fields:
                if field.name == "Winners":
                    winners_text = field.value
                    if winners_text and winners_text != "No winners!":
                        winners_count = len(
                            [line for line in winners_text.split("\n") if line.strip()]
                        )
                    break

    panel_embed = discord.Embed(
        title="🎮 Chat Game Admin Panel",
        description=f"Manage the **{game_name}** game below.",
        color=discord.Color.from_str(config.get("config", "EMBED_COLOR")),
        timestamp=datetime.now(timezone.utc),
    )
    panel_embed.add_field(
        name="📋 Game Information",
        value=(
            f"**Type:** {game_name}\n"
            f"**XP Multiplier:** {xp_mult:.1f}x\n"
            f"**Test Mode:** {'Yes' if test_mode else 'No'}\n"
            f"**Winners:** {winners_count}"
        ),
        inline=True,
    )
    actions_value = (
        "**Show Answer** - View the correct answer\n"
        "**Reset** - Reset game to original state\n"
        "**Reroll** - Get a new question/word\n"
        "**Toggle 2x** - Switch XP multiplier\n"
        "**End Game Now** - Immediately end the game\n"
        "**Show Activity** - View activity log"
    )
    if game_ended:
        actions_value += "\n\n*⚠️ Game has ended. Some actions may be limited.*"

    panel_embed.add_field(
        name="🔧 Available Actions",
        value=actions_value,
        inline=True,
    )
    panel_embed.add_field(
        name="🔗 Game Message",
        value=f"[Jump to Game Message]({message.jump_url})",
        inline=False,
    )

    
    logo_url = bot.app.embeds.get_logo_url(config.get("config", "LOGO"))
    panel_embed.set_footer(text=config.get("config", "FOOTER"), icon_url=logo_url)

    await interaction.response.send_message(
        embed=panel_embed, view=view, ephemeral=True
    )


class ChatGameAdmin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = ConfigManager.get_instance()
        self.logger = get_logger("Commands")


async def setup(bot):
    await bot.add_cog(ChatGameAdmin(bot))
    bot.tree.add_command(manage_chat_game)
