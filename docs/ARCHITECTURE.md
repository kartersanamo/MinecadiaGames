# Architecture

This document describes the core services, database usage, managers, and how the bot starts and runs.

---

## Entry point and startup

- **Entry:** `bot.py` → `main()` creates `MinecadiaBot`, gets token from `config.get('config', 'TOKEN')`, runs `bot.run(token)`.  
- **Setup:**  
  - `setup_hook`: Starts background DB pool init, starts `CacheManager` cleanup task, loads all extensions from `cogs/`.  
  - `on_ready`: Ensures GameManager exists and is initialized (chat + DM loops); loads Wordle, Minesweeper, Hangman listeners; registers persistent views; may restore active chat games.  
- **Extensions:** Every `.py` in `cogs/` (except names starting with `_`) is loaded as `cogs.<stem}`.

---

## Core

### ConfigManager (`core/config/manager.py`)

- Singleton. Loads JSON from `assets/Configs/`.  
- `get(config_name, key=None, default=None)`.  
- Special handling: `config` = merge of `bot` + `discord`; key mapping for backward compatibility.  
- Used everywhere for token, database, channels, roles, game options, leveling, milestones.

### DatabasePool (`core/database/pool.py`)

- Singleton async MySQL pool (aiomysql, DictCursor).  
- `get_instance()` then `initialize()` (or wait for background init in setup_hook).  
- Methods: `execute`, `execute_insert`, context manager for transactions.  
- Config: `config.get('config', 'DATABASE_CONFIG')` → host, port, user, password, database, autocommit.

### CacheManager (`core/cache/manager.py`)

- In-memory TTL cache. Singleton.  
- `get(key)`, `set(key, value, ttl=None)`, `delete(key)`, `clear()`.  
- Cleanup task started in setup_hook (expired entries removed periodically).

### Logging (`core/logging/setup.py`)

- `setup_logging()` called in bot init.  
- `get_logger(name)` for module-specific loggers.

---

## Database (main tables)

- **leveling** — user_id, xp, level (and any extra columns).  
- **xp_logs** — game_id, user_id, xp, channel_id, source, timestamp (or equivalent).  
- **user_achievements** — user_id, achievement_id, earned_at.  
- **user_badge_preferences** — user_id, selected_badge_id.  
- **games** — game_id, game_name, dm_game, refreshed_at, end_time, status, etc. (for active game tracking).  
- **users_<game>** — per-game tables (e.g. users_tictactoe, users_wordle, users_connectfour, users_memory, users_2048, users_minesweeper, users_hangman) for wins, scores, state.  
- **Counting / logs** — tables used by counter and logs cog (channel-specific counts, streaks, etc.).  

Schema is not fully listed here; refer to migrations or DB creation scripts if present.

---

## Managers

### GameManager (`managers/game_manager.py`)

- Holds `dm_games`: dict of game name → instance (Wordle, TicTacToe, Connect Four, Memory, 2048, Minesweeper, Hangman).  
- `_dm_game_loop`: Refreshes DM game message (e.g. embed + view) on an interval.  
- `_chat_game_loop`: Picks channel and game, starts chat game, sets timer; on timer end, ends game and may start next.  
- `_monitor_chat_game_task`: Restarts chat game task if it stops.  
- Uses ConfigManager and DatabasePool.

### LevelingManager (`managers/leveling.py`)

- **New API:** `LevelingManager()` (singleton) then `award_xp(user, xp, source, game_id, channel=..., bot=..., test_mode=...)`.  
- **Old API:** `LevelingManager(user, channel, client, xp, source, game_id, test_mode)` then `await manager.update()` (wraps award_xp).  
- Internals: debounce, load/create user stats, update leveling table, log to xp_logs, check level-up, run `_check_achievements` (chat game + total XP milestones), admin log, console log.  
- Level thresholds from config (`levels` / leveling).

### MilestonesManager (`managers/milestones.py`)

- Loads `milestones` config.  
- `check_achievements(user_id, game_type, metric, value, user=None, channel=None, client=None)`: evaluates thresholds, inserts into `user_achievements`, and if `user` is provided awards milestone XP via LevelingManager.  
- Other: get_user_achievements, get_user_badges, selected badge get/set, get_display_badge, get_milestone_progress, _get_current_metric_value (per-game queries).

---

## Utils

- **achievements** (`utils/achievements.py`): `check_game_achievements`, `check_dm_game_win`, `check_chat_game_play`, `check_level_achievement`, `check_xp_achievement`. All funnel through `check_achievements` with user/channel/client when applicable so milestone XP is granted.  
- **helpers** (`utils/helpers.py`): e.g. `get_last_game_id`, embed logo URL, etc.  
- **paginator** (`utils/paginator.py`): Paginated embeds (used in stats, leaderboards, etc.).  
- **chat_game_registry** (`utils/chat_game_registry.py`): Singleton registry of active chat games by message_id for admin and state access.  
- **game_state_manager** (`utils/game_state_manager.py`): If present, used for saving/loading game state.

---

## UI components

- **dm_games_view.py**: View for choosing a DM game (buttons).  
- **sendgames_view.py**: Flow for sending the games message and building leaderboard/embed data.  
- **all_time_leaderboard.py**: All-time leaderboard UI and badge resolution.  

Views are either registered persistently in `bot.py` or created when a command runs (e.g. send-games, milestones, statistics).

---

## Flow summary

1. Bot starts → config loaded, cache started, DB pool init in background, cogs loaded.  
2. On ready → GameManager inits (dm + chat loops), listeners (Wordle, Minesweeper, Hangman) added, persistent views registered.  
3. User runs `/send-games` or similar → message with DM games view (or channel-specific flow).  
4. User starts a DM game → game view in DM; on win/loss/cash out, game updates DB and awards XP and runs achievement checks (with user/channel/client so milestone XP is granted).  
5. Chat game loop posts a game → users answer; first correct gets XP via LevelingManager → _check_achievements runs → total_games and total_xp_all milestones checked and XP granted when new milestones are earned.  
6. Monthly wipe → wipe_levels awards monthly_leaderboard_champion and then calls LevelingManager.award_xp for that user.

---

## References

- Games and loops: [Games](GAMES.md).  
- XP and milestones: [Leveling & achievements](LEVELING_AND_ACHIEVEMENTS.md).  
- Config: [Configuration](CONFIGURATION.md).  
- Commands: [Commands & cogs](COMMANDS_AND_COGS.md).
