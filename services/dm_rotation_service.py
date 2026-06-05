"""DM game rotation and vault helpers — single source of truth for dm.json rotation state."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.config.manager import ConfigManager


def get_games_dict(dm_config: Dict[str, Any]) -> Dict[str, Any]:
    return dm_config.get("GAMES", {}) or dm_config.get("games", {}) or {}


def is_vaulted(game_config: Dict[str, Any]) -> bool:
    if "vaulted" in game_config:
        return bool(game_config["vaulted"])
    if "enabled" in game_config:
        return not bool(game_config["enabled"])
    return False


def get_rotation_games(dm_config: Dict[str, Any]) -> List[str]:
    games_dict = get_games_dict(dm_config)
    return [name for name, cfg in games_dict.items() if not is_vaulted(cfg)]


def get_vaulted_games(dm_config: Dict[str, Any]) -> List[str]:
    games_dict = get_games_dict(dm_config)
    return [name for name, cfg in games_dict.items() if is_vaulted(cfg)]


def get_rotation_delay(dm_config: Dict[str, Any]) -> int:
    delay = dm_config.get("DELAY") or dm_config.get("rotation_delay", 7200)
    return int(delay)


def _normalize_name(name: str) -> str:
    return name.lower().replace(" ", "")


def get_next_rotation_game(
    dm_config: Dict[str, Any], last_game_name: Optional[str]
) -> Optional[str]:
    rotation = get_rotation_games(dm_config)
    if not rotation:
        return None

    if not last_game_name:
        return rotation[0]

    all_names = list(get_games_dict(dm_config).keys())
    rotation_set = set(rotation)

    try:
        start_idx = next(
            i for i, n in enumerate(all_names) if _normalize_name(n) == _normalize_name(last_game_name)
        )
    except StopIteration:
        return rotation[0]

    for i in range(1, len(all_names) + 1):
        candidate = all_names[(start_idx + i) % len(all_names)]
        if candidate in rotation_set:
            return candidate

    return rotation[0]


def build_rotation_lines(
    active_game: str, dm_config: Dict[str, Any]
) -> Tuple[str, Optional[str]]:
    rotation = get_rotation_games(dm_config)
    vaulted = get_vaulted_games(dm_config)
    active_norm = _normalize_name(active_game)

    rotation_display = " → ".join(
        f"**{g}**" if _normalize_name(g) == active_norm else g for g in rotation
    )
    vaulted_display = f"**Vaulted:** {', '.join(vaulted)}" if vaulted else None
    return rotation_display, vaulted_display


def build_dm_rotation_embed_section(
    active_game: str, refreshed_at: int, dm_config: Dict[str, Any]
) -> str:
    delay = get_rotation_delay(dm_config)
    new_dm_game = refreshed_at + delay
    rotation_display, vaulted_display = build_rotation_lines(active_game, dm_config)

    lines = [
        f"✅ **Active DM Game**: {active_game}",
        f"🚨 **Next DM Game**: <t:{new_dm_game}:R>",
    ]
    if rotation_display:
        lines.append(f"-# {rotation_display}")
    else:
        lines.append("-# (no games in rotation)")
    if vaulted_display:
        lines.append(f"-# {vaulted_display}")
    return "\n".join(lines)


def set_game_vaulted(config: ConfigManager, game_name: str, vaulted: bool) -> None:
    config.set("dm_games", f"games.{game_name}.vaulted", vaulted)
    config.reload("dm_games")
