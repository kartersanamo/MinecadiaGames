import random
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

DEFAULT_COLORS = ["🟥", "🟧", "🟨", "🟩", "🟦", "🟪"]
DEFAULT_CODE_LENGTH = 4
DEFAULT_MAX_GUESSES = 8
DEFAULT_NUM_COLORS = 6


def evaluate_guess(secret: List[int], guess: List[int]) -> Tuple[int, int]:
    """Return (black_pegs, white_pegs) using standard Mastermind scoring."""
    black = 0
    secret_remaining: List[int] = []
    guess_remaining: List[int] = []

    for s, g in zip(secret, guess):
        if s == g:
            black += 1
        else:
            secret_remaining.append(s)
            guess_remaining.append(g)

    white = 0
    for g in guess_remaining:
        if g in secret_remaining:
            white += 1
            secret_remaining.remove(g)

    return black, white


def generate_secret(code_length: int, num_colors: int) -> List[int]:
    return [random.randint(0, num_colors - 1) for _ in range(code_length)]


def calculate_win_xp(
    guesses_used: int,
    max_guesses: int,
    win_min: int,
    win_max: int,
) -> int:
    if max_guesses <= 1:
        return win_max
    step = (win_max - win_min) // (max_guesses - 1)
    return max(win_min, win_max - (guesses_used - 1) * step)


@dataclass
class MastermindState:
    secret: List[int] = field(default_factory=list)
    guesses: List[List[int]] = field(default_factory=list)
    feedback: List[Tuple[int, int]] = field(default_factory=list)
    current_guess: List[int] = field(default_factory=list)
    max_guesses: int = DEFAULT_MAX_GUESSES
    code_length: int = DEFAULT_CODE_LENGTH
    num_colors: int = DEFAULT_NUM_COLORS
    game_ended: bool = False
    won: bool = False

    @classmethod
    def new(
        cls,
        *,
        max_guesses: int = DEFAULT_MAX_GUESSES,
        code_length: int = DEFAULT_CODE_LENGTH,
        num_colors: int = DEFAULT_NUM_COLORS,
    ) -> "MastermindState":
        return cls(
            secret=generate_secret(code_length, num_colors),
            max_guesses=max_guesses,
            code_length=code_length,
            num_colors=num_colors,
        )

    @classmethod
    def from_dict(cls, data: dict, colors: Optional[List[str]] = None) -> "MastermindState":
        del colors  # kept for API parity with other engines
        feedback_raw = data.get("feedback", [])
        feedback = [tuple(pair) for pair in feedback_raw]
        return cls(
            secret=list(data.get("secret", [])),
            guesses=[list(row) for row in data.get("guesses", [])],
            feedback=feedback,
            current_guess=list(data.get("current_guess", [])),
            max_guesses=int(data.get("max_guesses", DEFAULT_MAX_GUESSES)),
            code_length=int(data.get("code_length", DEFAULT_CODE_LENGTH)),
            num_colors=int(data.get("num_colors", DEFAULT_NUM_COLORS)),
            game_ended=bool(data.get("game_ended", False)),
            won=bool(data.get("won", False)),
        )

    def to_dict(self) -> dict:
        return {
            "secret": self.secret[:],
            "guesses": [row[:] for row in self.guesses],
            "feedback": [list(pair) for pair in self.feedback],
            "current_guess": self.current_guess[:],
            "max_guesses": self.max_guesses,
            "code_length": self.code_length,
            "num_colors": self.num_colors,
            "game_ended": self.game_ended,
            "won": self.won,
        }

    @property
    def guesses_used(self) -> int:
        return len(self.guesses)

    @property
    def guesses_remaining(self) -> int:
        return max(0, self.max_guesses - self.guesses_used)

    def _color_str(self, colors: List[str], color_idx: int) -> str:
        if 0 <= color_idx < len(colors):
            return colors[color_idx]
        return "?"

    def _format_guess_row(self, colors: List[str], row: List[int]) -> str:
        parts: List[str] = []
        for i in range(self.code_length):
            if i < len(row):
                parts.append(self._color_str(colors, row[i]))
            else:
                # Backticks prevent Discord from treating _ as italic markup.
                parts.append("`_`")
        return " ".join(parts)

    def _format_feedback(self, black: int, white: int) -> str:
        return "⚫" * black + "⚪" * white

    def render_embed_parts(
        self, colors: List[str], *, reveal_secret: bool = False
    ) -> dict:
        """Build embed description + guess/feedback field text."""
        description_lines: List[str] = []

        if reveal_secret or self.game_ended:
            secret_pegs = " ".join(self._color_str(colors, idx) for idx in self.secret)
            description_lines.append(f"**Secret:** {secret_pegs}")

        if self.game_ended:
            if self.won:
                description_lines.append(
                    f"🎉 **You cracked the code in {self.guesses_used} "
                    f"guess{'es' if self.guesses_used != 1 else ''}!**"
                )
            else:
                description_lines.append("❌ **Out of guesses!** Better luck next time.")
        else:
            description_lines.append(
                f"**Guesses left:** {self.guesses_remaining}/{self.max_guesses}"
            )

        guess_lines: List[str] = []
        feedback_lines: List[str] = []

        for i, (guess, (black, white)) in enumerate(
            zip(self.guesses, self.feedback), start=1
        ):
            guess_lines.append(f"Guess `{i}` {self._format_guess_row(colors, guess)}")
            feedback_lines.append(f"Guess `{i}` {self._format_feedback(black, white)}")

        if not self.game_ended and self.guesses_remaining > 0:
            guess_lines.append(
                f"**Current:** {self._format_guess_row(colors, self.current_guess)}"
            )
            feedback_lines.append("**Current:** —")

        return {
            "description": "\n\n".join(description_lines) if description_lines else "\u200b",
            "guesses": "\n".join(guess_lines) if guess_lines else "No guesses yet.",
            "feedback": "\n".join(feedback_lines) if feedback_lines else "—",
        }

    def render_board(self, colors: List[str], *, reveal_secret: bool = False) -> str:
        """Legacy single-block board text (used if embed fields are unavailable)."""
        parts = self.render_embed_parts(colors, reveal_secret=reveal_secret)
        lines = [parts["description"], "", "**Guesses**", parts["guesses"], "", "**Feedback**", parts["feedback"]]
        return "\n".join(lines)

    def place_peg(self, color_idx: int) -> bool:
        """Place a peg. Returns True if a full row was just completed."""
        if self.game_ended:
            return False
        if color_idx < 0 or color_idx >= self.num_colors:
            return False
        if len(self.current_guess) >= self.code_length:
            return False
        if self.guesses_used >= self.max_guesses:
            return False

        self.current_guess.append(color_idx)
        if len(self.current_guess) < self.code_length:
            return False

        black, white = evaluate_guess(self.secret, self.current_guess)
        self.guesses.append(self.current_guess[:])
        self.feedback.append((black, white))
        self.current_guess.clear()

        if black == self.code_length:
            self.won = True
            self.game_ended = True
        elif self.guesses_used >= self.max_guesses:
            self.game_ended = True

        return True

    def undo_peg(self) -> bool:
        if self.game_ended or not self.current_guess:
            return False
        self.current_guess.pop()
        return True
