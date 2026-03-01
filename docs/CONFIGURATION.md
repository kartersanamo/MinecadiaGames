# Configuration

This document describes how configuration is loaded, which files exist, and the main keys used by the bot. **Do not commit real tokens or database passwords;** use environment variables or local-only overrides.

---

## ConfigManager

- **Singleton:** `ConfigManager.get_instance()`.  
- **Location:** By default, config directory is `assets/Configs` (relative to the project root).  
- **API:** `config.get(config_name, key=None, default=None)`.  
  - If `key` is omitted, the whole config (dict) for `config_name` is returned.  
  - If `key` is given, that key is resolved (with backward-compat mapping when applicable) and the value returned.  
- **Caching:** Configs are loaded and cached per `config_name`. File locks are used for thread-safe reads.  
- **Backward compatibility:** The name `'config'` is special: it merges `bot.json` and `discord.json`. Many legacy keys (e.g. `TOKEN`, `DATABASE_CONFIG`, `ADMIN_ROLES`) are mapped to the merged structure (e.g. `token`, `database`, `permissions.admin_roles`). See `core/config/manager.py` for the full mapping.

---

## Main config files

| File | Purpose |
|------|---------|
| `assets/Configs/bot.json` | Token, presence, database connection, embed defaults (color, footer, logo). |
| `assets/Configs/discord.json` | Guild ID, roles, channel IDs (admin logs, logs, tickets, announce), permissions (admin/staff roles), etc. When using `config`, this is merged with `bot.json`. |
| `assets/Configs/config.json` | Legacy/alternate; may hold same keys as bot + discord. ConfigManager can merge from bot + discord when you request `'config'`. |
| `assets/Configs/dm_games.json` | Global DM delay, button cooldown; per-game settings under `GAMES` (Wordle, TicTacToe, Connect Four, Memory, 2048, Minesweeper, Hangman). |
| `assets/Configs/chat_games.json` | Chat game delay (LOWER/UPPER), channels with chance weights, winners count, game length, XP (base + position). High-level game list. |
| `assets/Configs/games/*.json` | Per–chat-game data: trivia questions, unscramble words, flag/math/emoji quiz data, etc. |
| `assets/Configs/leveling.json` | Leveling system (often used in conjunction with levels data). |
| `assets/Configs/levels.json` | Level thresholds (level number → XP required). Used for level calculation. |
| `assets/Configs/milestones.json` | All milestone definitions by game type and metric (wins, total_games, best_score, level, total_xp_all, leaderboard_first). |
| `assets/Configs/rewards.json` | Rewards / winner messages (e.g. monthly wipe text). |
| `assets/Configs/winners.json` | Winner-related copy (titles, placeholders). |

---

## Key mappings (when using `config`)

When you call `config.get('config', 'KEY')`, the manager may translate to the merged structure:

- `TOKEN` → `token`  
- `DATABASE_CONFIG` → `database` (host, port, user, password, database, autocommit)  
- `ADMIN_ROLES` → `permissions.admin_roles`  
- `STAFF_ROLES` → `permissions.staff_roles`  
- `EMBED_COLOR`, `FOOTER`, `LOGO` → `embed.color`, `embed.footer`, `embed.logo`  
- `GUILD_ID` → `guild_id`  
- `ADMIN_LOGS` → `channels.admin_logs`  
- `LOGS_CHANNEL` → `channels.logs`  
- `DISCORD_TICKETS` → `channels.tickets_category`  
- `ANNOUNCE_CHANNELS` → `channels.announce`  
- Plus others (see `core/config/manager.py`).

So code that uses `config.get('config', 'DATABASE_CONFIG')` or `config.get('config', 'TOKEN')` still works via this mapping.

---

## Chat games config shape

- `config.get('chat_games')` returns the merged chat games config.  
- Legacy keys are mapped when accessed by key: e.g. `DELAY` (LOWER/UPPER), `CHANNELS` (channel ID + chance), `WINNERS`, `GAME_LENGTH`, `XP` (XP_ADD, XP_LOWER by position), `GAMES` (per-game configs loaded from `games/trivia`, `games/unscramble`, etc.).  
- See `core/config/manager.py` for the exact `chat_games` key mappings.

---

## Security

- **Token:** Store in `bot.json` or via env; never commit.  
- **Database:** Store credentials in `bot.json` (or merged config) or env; never commit.  
- Prefer a local `bot.local.json` or env-based override in production.

---

## References

- Where config is used: [Architecture](ARCHITECTURE.md).  
- Game-specific options: [Games](GAMES.md).  
- Level/milestone config: [Leveling & achievements](LEVELING_AND_ACHIEVEMENTS.md).
