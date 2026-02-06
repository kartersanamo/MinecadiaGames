from typing import Optional, List, Dict, Any
from core.database.pool import DatabasePool
from core.config.manager import ConfigManager
import discord
import os


def get_embed_logo_url(logo_path: Optional[str]) -> Optional[str]:
    if not logo_path:
        return None

    if logo_path.startswith(("http://", "https://")):
        return logo_path

    if os.path.isfile(logo_path):
        filename = os.path.basename(logo_path)
        return f"attachment://{filename}"

    return None


async def get_last_game_id(game_name: str) -> Optional[int]:
    db = await DatabasePool.get_instance()
    rows = await db.execute(
        "SELECT game_id FROM games WHERE game_name = %s ORDER BY game_id DESC LIMIT 1",
        (game_name,)
    )
    return rows[0]['game_id'] if rows else None


async def has_played_game(game_name: str, user_id: int, game_id: int) -> bool:
    db = await DatabasePool.get_instance()
    safe_game_name = game_name.lower().replace(" ", "")
    rows = await db.execute(
        f"SELECT user_id FROM users_{safe_game_name} WHERE game_id = %s AND user_id = %s",
        (game_id, user_id)
    )
    return len(rows) > 0


async def get_last_dm_game_info() -> Optional[Dict[str, Any]]:
    db = await DatabasePool.get_instance()
    rows = await db.execute(
        "SELECT game_name, game_id FROM games WHERE dm_game = TRUE ORDER BY game_id DESC LIMIT 1"
    )
    return rows[0] if rows else None


async def can_dm_user(user: discord.User) -> bool:
    try:
        await user.send()
        return True
    except discord.Forbidden:
        return False
    except discord.HTTPException:
        return True


async def get_recent_games() -> tuple[List[str], List[str]]:
    db = await DatabasePool.get_instance()
    rows = await db.execute("SELECT * FROM games ORDER BY refreshed_at DESC")
    
    game_list = []
    game_str = []
    
    for row in rows:
        game_str.append(
            f"`#{row['game_id']}` **{row['game_name'].title()}** <t:{row['refreshed_at']}:R>"
        )
        game_list.append(f"{row['game_id']} {row['game_name'].title()}")
    
    return game_str, game_list


async def check_dm_game_requirements(
    interaction: discord.Interaction,
    game_name: str,
    config: ConfigManager
) -> tuple[bool, Optional[int], Optional[str]]:
    verified_role_id = config.get('config', 'VERIFIED_ROLE')
    if verified_role_id and interaction.guild:
        verified_role = interaction.guild.get_role(verified_role_id)
        if verified_role and verified_role not in interaction.user.roles:
            return False, None, f"You need the {verified_role.mention} role to play games!"
    
    last_game_info = await get_last_dm_game_info()
    if not last_game_info:
        return False, None, "No active game found"
    
    last_game_id = last_game_info['game_id']
    last_game_name = last_game_info['game_name']
    
    if last_game_name.lower() != game_name.lower():
        return False, None, f"This is not the most recent game. Only {last_game_name} is available."
    
    if await has_played_game(game_name, interaction.user.id, last_game_id):
        return False, None, f"You have already started {game_name} game #{last_game_id}"
    
    if not await can_dm_user(interaction.user):
        return False, None, f"I cannot send you a DM! Please enable DMs to play {game_name}."
    
    return True, last_game_id, None

