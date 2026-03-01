# Games (DM & Chat)

This document covers all playable games, where they’re configured, how XP and achievements are tied in, and practice mode.

---

## DM games

Played in DMs. Triggered from the DM games UI (e.g. **Send Games** flow). Each game has its own cooldown and optional per-game config in `assets/Configs/dm_games.json` under `GAMES`.

| Game | Module | Config key | Main features |
|------|--------|------------|----------------|
| **Wordle** | `games/dm/wordle.py` | `Wordle` | Guess the word in 6 tries; `WORDS_FILE` in config. DM listener for message-based guesses. |
| **Tic-Tac-Toe** | `games/dm/tictactoe.py` | `TicTacToe` | PvP vs bot. Win XP range `WIN_XP.LOWER`/`UPPER`. Cooldown, button cooldown. |
| **Connect Four** | `games/dm/connect_four.py` | `Connect Four` | Grid with image generation (`base_image_path`, `output_image_path`, piece paths). Win XP. |
| **Memory** | `games/dm/memory.py` | `Memory` | Card flip with custom emojis (`EMOJIS`), `TRIES` limit. Match XP and Win XP ranges. |
| **2048** | `games/dm/twenty_forty_eight.py` | `2048` | Slide puzzle; win/cash out/loss. Best score and win milestones. XP from score/highest tile. |
| **Minesweeper** | `games/dm/minesweeper.py` | `Minesweeper` | Grid with reveal/flag. DM listener for flagging. Win XP. |
| **Hangman** | `games/dm/hangman.py` | `Hangman` | `MAX_WRONG`, `WORDS_FILE`. Win XP; two code paths both call `check_dm_game_win`. |

**Achievements (wins):** After a win, each DM game calls `check_dm_game_win(user, game_type, channel, bot)` from `utils.achievements`, which uses `check_game_achievements(..., "wins", win_count)` and thus `MilestonesManager.check_achievements` with `user`/`channel`/`client`. Milestone XP is granted via `LevelingManager.award_xp` in `milestones.check_achievements`.

**2048 best score:** 2048 also calls `milestones_manager.check_achievements(..., "best_score", self.score, user=..., channel=..., client=...)` on win/loss/cash out so best-score milestones grant XP.

**Config:** `assets/Configs/dm_games.json` — global `DELAY`, `BUTTON_COOLDOWN`, then `GAMES.<name>` for per-game cooldowns, images, XP ranges, word lists, etc.

---

## Chat games

Run in a single channel on a timer. The **GameManager** chat loop picks a channel (from `CHANNELS` with `CHANCE`), then a game, posts the game message, and tracks time. Winners get position-based XP (e.g. 1st–3rd get more). Config: `assets/Configs/chat_games.json` and per-game files under `assets/Configs/games/`.

| Game | Module | Config | Notes |
|------|--------|--------|--------|
| **Trivia** | `games/chat/trivia.py` | `games/trivia.json` | Per-guild questions, difficulty. First correct answer wins. |
| **Unscramble** | `games/chat/unscramble.py` | `games/unscramble.json` | Per-channel word lists; first correct unscramble wins. |
| **Flag Guesser** | `games/chat/flag_guesser.py` | `games/flag_guesser.json` | Flag image + API; first correct country wins. |
| **Math Quiz** | `games/chat/math_quiz.py` | `games/math_quiz.json` | Problem types and accepted formats; first correct answer wins. |
| **Emoji Quiz** | `games/chat/emoji_quiz.py` | `games/emoji_quiz.json` | Emoji-based clues; first correct answer wins. |
| **Guess the Number** | `games/chat/guess_the_number.py` | In chat config | Number range; first correct guess wins. |

**XP:** When a chat game ends, the view awards XP via `LevelingManager` (position-based from `XP.XP_ADD` and `XP.XP_LOWER`). Then `LevelingManager.award_xp` triggers `_check_achievements`, which runs `check_chat_game_play` and `check_xp_achievement`. Both go through `check_game_achievements` with `user`/`channel`/`client`, so milestone XP is granted for **total_games** and **total_xp_all** milestones.

**Config:**  
- `chat_games.json`: `DELAY` (LOWER/UPPER seconds between games), `CHANNELS`, `WINNERS`, `GAME_LENGTH`, `XP`, and high-level `GAMES` mapping.  
- Per-game: `assets/Configs/games/trivia.json`, `unscramble.json`, `flag_guesser.json`, `math_quiz.json`, `emoji_quiz.json`, `chat.json` (etc.) for questions, word lists, and options.

---

## Practice mode

**Command:** `/practice` (in #games). Starts a test-mode session for:

- Trivia  
- Math Quiz  
- Flag Guesser  
- Unscramble  
- Emoji Quiz  

Practice uses the same game views but with **test_mode=True**: no XP written, no DB progress, no level-up or milestone XP. Implemented in `cogs/practice.py` and the respective chat game classes.

---

## Game manager

- **GameManager** (`managers/game_manager.py`): Holds `dm_games` dict (one instance per DM game), runs `_dm_game_loop` and `_chat_game_loop`, restores active chat games after restart.  
- **ChatGameRegistry** (`utils/chat_game_registry.py`): Singleton registry of active chat games by message ID (for context menu / admin and state inspection).  
- **Send Games / DM games UI**: `cogs/sendgames.py`, `ui/sendgames_view.py`, `ui/dm_games_view.py` — send the prompts that let users start DM games or open the DM game menu.

---

## References

- Milestones (wins, total_games, best_score, level, total_xp_all): [Leveling & achievements](LEVELING_AND_ACHIEVEMENTS.md).  
- Config keys and files: [Configuration](CONFIGURATION.md).  
- How games are started and how the bot registers views: [Architecture](ARCHITECTURE.md).
