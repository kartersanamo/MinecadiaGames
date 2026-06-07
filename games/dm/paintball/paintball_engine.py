import random
from dataclasses import dataclass
from typing import Any, Dict, Optional

POSITION_NAMES = ["Left", "Center", "Right"]

PHASE_SELECTING = "selecting"
PHASE_REVEALING = "revealing"
PHASE_ENDED = "ended"


def format_lives(lives: int, max_lives: int) -> str:
    remaining = max(0, min(lives, max_lives))
    lost = max_lives - remaining
    return "❤️" * remaining + "🖤" * lost


def calculate_xp(win_min: int, win_max: int) -> int:
    return random.randint(win_min, win_max)


@dataclass
class RoundResult:
    bot_hide: int
    bot_shoot: int
    player_hit: bool
    bot_hit: bool

    def to_dict(self) -> dict:
        return {
            "bot_hide": self.bot_hide,
            "bot_shoot": self.bot_shoot,
            "player_hit": self.player_hit,
            "bot_hit": self.bot_hit,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RoundResult":
        return cls(
            bot_hide=int(data["bot_hide"]),
            bot_shoot=int(data["bot_shoot"]),
            player_hit=bool(data["player_hit"]),
            bot_hit=bool(data["bot_hit"]),
        )


@dataclass
class PaintballState:
    max_lives: int = 3
    player_lives: int = 3
    bot_lives: int = 3
    player_hide: Optional[int] = None
    player_shoot: Optional[int] = None
    phase: str = PHASE_SELECTING
    round: int = 1
    game_ended: bool = False
    last_round: Optional[RoundResult] = None

    def clear_selection(self) -> None:
        self.player_hide = None
        self.player_shoot = None

    def ready_to_fire(self) -> bool:
        return (
            self.phase == PHASE_SELECTING
            and self.player_hide is not None
            and self.player_shoot is not None
        )

    def bot_pick(self) -> tuple[int, int]:
        return random.randint(0, 2), random.randint(0, 2)

    def resolve_round(self, bot_hide: int, bot_shoot: int) -> RoundResult:
        player_hit = bot_shoot == self.player_hide
        bot_hit = self.player_shoot == bot_hide

        if player_hit:
            self.player_lives = max(0, self.player_lives - 1)
        if bot_hit:
            self.bot_lives = max(0, self.bot_lives - 1)

        result = RoundResult(
            bot_hide=bot_hide,
            bot_shoot=bot_shoot,
            player_hit=player_hit,
            bot_hit=bot_hit,
        )
        self.last_round = result
        return result

    def outcome(self) -> Optional[str]:
        """Return 'won', 'lost', 'tied', or None if game continues."""
        if self.player_lives <= 0 and self.bot_lives <= 0:
            return "tied"
        if self.bot_lives <= 0:
            return "won"
        if self.player_lives <= 0:
            return "lost"
        return None

    def format_round_result(self) -> str:
        if not self.last_round:
            return ""
        r = self.last_round
        lines = [
            f"**Round {self.round}** — Both players popped up and fired!",
            f"You hid **{POSITION_NAMES[self.player_hide]}** and shot **{POSITION_NAMES[self.player_shoot]}**.",
            f"Bot hid **{POSITION_NAMES[r.bot_hide]}** and shot **{POSITION_NAMES[r.bot_shoot]}**.",
        ]
        if r.player_hit and r.bot_hit:
            lines.append("💥 **Both hit!** You and the bot each lose a life.")
        elif r.player_hit:
            lines.append("💥 **You got hit!** You lose a life.")
        elif r.bot_hit:
            lines.append("🎯 **Direct hit!** The bot loses a life.")
        else:
            lines.append("Both missed — no lives lost.")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "max_lives": self.max_lives,
            "player_lives": self.player_lives,
            "bot_lives": self.bot_lives,
            "player_hide": self.player_hide,
            "player_shoot": self.player_shoot,
            "phase": self.phase,
            "round": self.round,
            "game_ended": self.game_ended,
        }
        if self.last_round:
            data["last_round"] = self.last_round.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "PaintballState":
        last_round = None
        if data.get("last_round"):
            last_round = RoundResult.from_dict(data["last_round"])
        return cls(
            max_lives=int(data.get("max_lives", 3)),
            player_lives=int(data.get("player_lives", 3)),
            bot_lives=int(data.get("bot_lives", 3)),
            player_hide=data.get("player_hide"),
            player_shoot=data.get("player_shoot"),
            phase=data.get("phase", PHASE_SELECTING),
            round=int(data.get("round", 1)),
            game_ended=bool(data.get("game_ended", False)),
            last_round=last_round,
        )
