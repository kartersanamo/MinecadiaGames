from __future__ import annotations

import uuid
from pathlib import Path


class AssetPathService:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    ASSETS_DIR = PROJECT_ROOT / "assets"
    GENERATED_IMAGES_DIR = ASSETS_DIR / "Images" / "generated"
    LOGO_PATH = "assets/Images/Logo.png"

    @classmethod
    def generated_image_path(cls, prefix: str, game_id: int | str) -> Path:
        cls.GENERATED_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        return cls.GENERATED_IMAGES_DIR / f"{prefix}_{game_id}_{uuid.uuid4().hex[:8]}.png"
