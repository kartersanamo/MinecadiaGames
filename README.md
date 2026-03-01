# Minecadia Games Bot

A full-featured Discord bot for the Minecadia community: **leveling**, **achievements**, **DM games**, **chat games**, **counting**, **daily rewards**, **leaderboards**, and **admin tooling**. All game progress and XP are persisted to a MySQL database with config-driven behavior.

---

## Table of contents

- [Features overview](#features-overview)
- [Tech stack](#tech-stack)
- [Quick start](#quick-start)
- [Project structure](#project-structure)
- [Documentation index](#documentation-index)
- [Configuration](#configuration)
- [Running the bot](#running-the-bot)
- [Contributing](#contributing)

---

## Features overview

| Area | Description |
|------|-------------|
| **DM games** | Wordle, Tic-Tac-Toe, Connect Four, Memory, 2048, Minesweeper, Hangman — play in DMs with cooldowns, XP, and win tracking. See [Games (DM & chat)](docs/GAMES.md). |
| **Chat games** | Trivia, Unscramble, Flag Guesser, Math Quiz, Emoji Quiz, Guess the Number — auto-rotating games in configured channels with position-based XP. |
| **Leveling & XP** | XP from games, daily rewards, milestones, and manual grants; levels from `levels`/`leveling` config; debouncing, admin logs, level-up DMs. See [Leveling & achievements](docs/LEVELING_AND_ACHIEVEMENTS.md). |
| **Achievements & milestones** | Per-game and global milestones (wins, total games, best score, level, total XP); badge selection and display; milestone XP granted via LevelingManager. |
| **Counting** | Counting channel with streaks and statistics; optional role rewards. |
| **Daily rewards** | Cooldown-based daily XP claim. |
| **Leaderboards** | Monthly wipe, all-time XP/level leaderboards, top winners, monthly champion achievement + XP. |
| **Statistics** | Per-user game stats (wins, plays, scores) and level/XP overview. |
| **Practice mode** | Test-mode games (no XP/DB) for Trivia, Math Quiz, Flag Guesser, Unscramble, Emoji Quiz in #games. |
| **Admin** | Config get/set/reload, game toggles, force chat game, add/remove XP, wipe levels, logs viewer, chat game admin UI. |

---

## Tech stack

- **Python 3** with **discord.py** (commands + app_commands)
- **MySQL** via **aiomysql** (async connection pool)
- **JSON configs** under `assets/Configs/` (games, leveling, milestones, rewards, etc.)
- **Singleton/core services**: ConfigManager, DatabasePool, CacheManager, LevelingManager, MilestonesManager, GameManager

---

## Quick start

1. **Clone and install**

   ```bash
   git clone <repo_url>
   cd MinecadiaGames
   pip install discord.py aiomysql pandas   # add any other deps from imports; or create requirements.txt
   ```

2. **Configure**

   - Copy/edit `assets/Configs/bot.json` and `assets/Configs/discord.json` (or merged `config`). Set `token` and `database` (see [Configuration](docs/CONFIGURATION.md)).
   - Ensure MySQL is running and the database/schema exist (see [Architecture](docs/ARCHITECTURE.md#database)).

3. **Run**

   ```bash
   python bot.py
   ```

   The bot loads all cogs from `cogs/`, initializes the database pool and cache, starts the GameManager (chat + DM loops), and registers persistent views.

---

## Project structure

```
MinecadiaGames/
├── bot.py                 # Entry point, MinecadiaBot, extension loading, view registration
├── assets/Configs/        # JSON configs (bot, discord, dm_games, chat_games, milestones, levels, etc.)
├── core/                  # Config, database pool, cache, logging
├── cogs/                  # Discord cogs (commands + listeners)
├── games/                 # Game logic
│   ├── base/              # Base classes (game, dm_game, chat_game)
│   ├── dm/                # Wordle, TicTacToe, Connect Four, Memory, 2048, Minesweeper, Hangman
│   └── chat/              # Trivia, Unscramble, Flag Guesser, Math Quiz, Emoji Quiz, Guess the Number
├── managers/              # GameManager, LevelingManager, MilestonesManager
├── ui/                    # Shared views (DM games menu, sendgames, leaderboards)
├── utils/                 # Achievements, helpers, paginator, chat game registry
└── docs/                  # Detailed documentation (linked below)
```

---

## Documentation index

| Document | Contents |
|----------|----------|
| [Games (DM & chat)](docs/GAMES.md) | All DM and chat games, config locations, XP, achievements, practice mode. |
| [Leveling & achievements](docs/LEVELING_AND_ACHIEVEMENTS.md) | XP flow, level formula, milestones, badge selection, where XP is granted (including all games + monthly champion). |
| [Configuration](docs/CONFIGURATION.md) | Config files, `ConfigManager` keys, env/security notes. |
| [Commands & cogs](docs/COMMANDS_AND_COGS.md) | Slash commands, prefix commands, and cog list. |
| [Architecture](docs/ARCHITECTURE.md) | Core services, database usage, managers, run flow. |

---

## Configuration

- **Bot token & database**: Set in `assets/Configs/bot.json` (or merged `config`). The app reads `config` as a merge of `bot` + `discord` (see [Configuration](docs/CONFIGURATION.md)).
- **Game behavior**: DM games → `assets/Configs/dm_games.json`; chat games → `assets/Configs/chat_games.json` and `assets/Configs/games/*.json`.
- **Leveling**: `assets/Configs/leveling.json` and `assets/Configs/levels.json`.
- **Milestones**: `assets/Configs/milestones.json`.
- **Rewards / winners**: `assets/Configs/rewards.json`, `assets/Configs/winners.json`.

Do not commit real tokens or database credentials; use env vars or local overrides as needed.

---

## Running the bot

```bash
python bot.py
```

- Requires a valid Discord token and MySQL reachable with the configured `DATABASE_CONFIG`.
- Cogs are loaded from `cogs/` (all `.py` files that don’t start with `_`).
- On ready: GameManager starts chat and DM game loops; Wordle, Minesweeper, and Hangman listeners are registered; persistent views (config, logs, milestones, statistics, paginator, chat game admin) are added.

---

## Contributing

- Follow existing patterns: config-driven options, async DB via `DatabasePool`, XP via `LevelingManager`, achievements via `utils.achievements` and `MilestonesManager.check_achievements` with `user`/`channel`/`client` when awarding milestone XP.
- New games: DM games extend the base in `games/dm/` and register in `GameManager.dm_games`; chat games extend the base in `games/chat/` and are invoked by the chat game loop (see [Games](docs/GAMES.md) and [Architecture](docs/ARCHITECTURE.md)).

---

For full detail on every feature, use the [documentation index](#documentation-index) above.
