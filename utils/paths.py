"""Filesystem paths for MinecadiaGames (single assets/ tree)."""
from __future__ import annotations

from pathlib import Path
import uuid

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"
GENERATED_IMAGES_DIR = ASSETS_DIR / "Images" / "generated"
LOGO_PATH = "assets/Images/Logo.png"


def generated_image_path(prefix: str, game_id: int | str) -> Path:
    """Path for a ephemeral game image; directory is created if needed."""
    GENERATED_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    return GENERATED_IMAGES_DIR / f"{prefix}_{game_id}_{uuid.uuid4().hex[:8]}.png"
