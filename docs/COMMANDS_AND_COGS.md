# Commands & Cogs

This document lists the Discord cogs and their slash/prefix commands. All cogs live in `cogs/` and are loaded automatically by `bot.py` (any `.py` that does not start with `_`).

---

## Slash commands (app_commands)

| Command | Cog | Description |
|---------|-----|-------------|
| `/level` | level | View your (or target user’s) level and XP. |
| `/milestones` | milestones | View milestones/achievements and badge selection. |
| `/statistics` | statistics | View your game statistics (wins, plays, scores, etc.). |
| `/daily` | daily | Claim daily XP reward (cooldown-based). |
| `/practice` | practice | Start a practice (test) game in #games (Trivia, Math Quiz, Flag Guesser, Unscramble, Emoji Quiz). |
| `/send-games` | sendgames | Send the games prompt/message (triggers DM games UI). |
| `/game-manager` | game_manager_cog | Manage chat and DM games (admin). |
| `/game-status` | game_control | View current game status. |
| `/toggle-chat-games` | game_control | Turn chat games on/off. |
| `/toggle-dm-games` | game_control | Turn DM games on/off. |
| `/force-chat-game` | game_control | Force start a chat game immediately. |
| `/test-game` | test_game | Test a chat or DM game (admin). |
| `/wipe-levels` | wipe_levels | Wipe levels and run monthly winner logic (admin). |
| `/add-xp` | add_xp | Add or remove XP from a member (admin). |
| `/config-get` | config_management | Get a configuration value. |
| `/config-set` | config_management | Set a configuration value. |
| `/config-reload` | config_management | Reload a configuration file. |
| `/config-manager` | config_management | Open interactive configuration manager. |
| `/logs` | logs | View detailed system logs (admin). |
| `/countingstats` | counting_stats | View counting channel statistics. |

---

## Prefix commands (commands)

| Command | Cog | Description |
|---------|-----|-------------|
| `.resetcount` | counter | Reset counting (admin/debug). |

(Other interactions are mostly buttons/selects from views, not prefix commands.)

---

## Cogs list (overview)

| Cog file | Purpose |
|----------|---------|
| `add_xp.py` | Add/remove XP; uses LevelingManager and checks level/xp achievements. |
| `chat_game_admin.py` | Admin UI for chat games (view/alter state); no slash command, view-only registration. |
| `config_management.py` | Config get/set/reload and config manager view. |
| `counter.py` | Counting channel logic, streaks, optional XP. |
| `counting_stats.py` | Counting statistics command. |
| `daily.py` | Daily XP claim with cooldown. |
| `game_control.py` | Toggle chat/DM games, game status, force chat game. |
| `game_manager_cog.py` | Game manager UI and control. |
| `level.py` | Level and XP display. |
| `logs.py` | Logs viewer (admin). |
| `milestones.py` | Milestones/achievements and badge selection UI. |
| `practice.py` | Practice (test) mode for chat games. |
| `sendgames.py` | Send games message and views. |
| `statistics.py` | User game statistics. |
| `test_game.py` | Test a single game (admin). |
| `tips.py` | Tips (no slash command; view/listeners if any). |
| `wipe_levels.py` | Wipe leveling leaderboards, assign monthly champion, award milestone XP. |

---

## Listeners (non-command)

- **WordleListener** (from `games/dm/wordle.py`): Handles DM messages for Wordle guesses.  
- **MinesweeperListener** (from `games/dm/minesweeper.py`): Handles DM interactions for Minesweeper (e.g. flagging).  
- **HangmanListener** (from `games/dm/hangman.py`): Handles DM messages for Hangman guesses.  

These are added in `bot.py` `on_ready` after GameManager is initialized.

---

## Persistent views

Registered in `bot.py` so they survive restarts:

- ConfigManagerView, ConfigViewer  
- LogsView  
- MilestonesView  
- StatisticsView  
- Paginator  
- ChatGameAdminView  

DM games view and Send Games view are created when the user runs `/send-games` or the equivalent flow.

---

## References

- How cogs are loaded: [Architecture](ARCHITECTURE.md).  
- Level/XP and milestones: [Leveling & achievements](LEVELING_AND_ACHIEVEMENTS.md).  
- Config keys used by commands: [Configuration](CONFIGURATION.md).
