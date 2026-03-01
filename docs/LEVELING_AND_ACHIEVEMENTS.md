# Leveling & Achievements

This document describes the leveling system, XP sources, milestone/achievement flow, and where XP is **always** granted via the database when a user earns a milestone.

---

## Leveling system

- **Levels** are derived from total XP using thresholds in `assets/Configs/levels.json` (or `leveling.json`).  
- **Total XP** is stored in the `leveling` table and also logged per award in `xp_logs` (user_id, xp, source, game_id, channel_id, timestamp).  
- **LevelingManager** (`managers/leveling.py`): Singleton-style API. Use `LevelingManager()` then `award_xp(user, xp, source, game_id, channel=..., bot=..., test_mode=...)` for all XP grants.  
- **Debouncing:** Optional per-user debounce to avoid duplicate XP in a short window.  
- **Level-up:** On level-up the bot can DM the user and run `check_level_achievement` (level milestones).  
- **Admin logging:** XP can be logged to an admin channel (config: `ADMIN_LOGS`).

---

## XP sources

| Source | Where | DB write |
|--------|--------|----------|
| DM game win | Each DM game on win | `LevelingManager.award_xp` in game code |
| Chat game finish | Chat game view on correct answer / win | `LevelingManager.award_xp` in view |
| Milestone / achievement | `MilestonesManager.check_achievements` when `user` is provided | `LevelingManager.award_xp` inside `check_achievements` |
| Daily reward | `/daily` in `cogs/daily.py` | `LevelingManager.award_xp` |
| Counting | Optional XP in `cogs/counter.py` | Via LevelingManager |
| Manual | `/add-xp` in `cogs/add_xp.py` | LevelingManager + level recalc |
| Monthly champion | `cogs/wipe_levels.py` after awarding `monthly_leaderboard_champion` | `LevelingManager.award_xp` right after `_award_achievement` |

All of the above go through `LevelingManager.award_xp`, which updates the leveling table and inserts into `xp_logs` (and optionally notifies level-up / admin log).

---

## Achievements & milestones

- **Definitions:** `assets/Configs/milestones.json` — per game type and metric (e.g. TicTacToe wins, 2048 best_score, Global level, total_xp_all). Each milestone has id, name, threshold, emoji.  
- **Storage:** Earned achievements are stored in `user_achievements` (user_id, achievement_id, earned_at).  
- **MilestonesManager** (`managers/milestones.py`):  
  - `check_achievements(user_id, game_type, metric, value, user=None, channel=None, client=None)` — checks thresholds, calls `_award_achievement` (DB insert), then **if `user` is not None** computes milestone XP (tier-based 400–700 or `milestone['xp']`) and calls `LevelingManager().award_xp(...)`. So **any time a milestone is awarded and `user` is passed, XP is granted via the database.**  
  - Other methods: `get_user_achievements`, `get_user_badges`, `get_selected_badge`, `set_selected_badge`, `get_display_badge`, `get_milestone_progress`, etc.

---

## Where milestone XP is granted (all paths)

Ensuring **every** milestone award grants XP:

1. **DM game wins (all games)**  
   Games call `check_dm_game_win(user, game_type, channel, bot)` → `check_game_achievements(..., user=user, channel=channel, client=client)` → `check_achievements(..., user=user, channel=..., client=...)`. So wins milestones get XP.

2. **2048 best_score**  
   All three call sites (win, loss, cash out) call `check_achievements(..., user=interaction.user, channel=interaction.channel, client=self.bot)`. So best_score milestones get XP.

3. **Chat games (total_games & total_xp_all)**  
   When any XP is awarded (e.g. from a chat game), `LevelingManager.award_xp` runs `_check_achievements` → `check_chat_game_play` and `check_xp_achievement` → both call `check_game_achievements` with user/channel/client. So total_games and total_xp_all milestones get XP.

4. **Level milestones**  
   On level-up, leveling code calls `check_level_achievement(user, new_level, channel, bot)` → `check_game_achievements(..., user=..., channel=..., client=...)`. So level milestones get XP.

5. **Monthly leaderboard champion**  
   In `cogs/wipe_levels.py`, after `_award_achievement` for `monthly_leaderboard_champion`, the cog gets the member and calls `LevelingManager().award_xp(..., xp=550, ...)`. So this one-off milestone also grants XP.

**Summary:** No milestone is awarded without a corresponding `LevelingManager.award_xp` call when the award path includes a user (or member) and context; the only direct `_award_achievement` outside `check_achievements` is monthly champion, and that path explicitly awards XP right after.

---

## Badges

- Users can **select a badge** (achievement) to display next to their name.  
- `MilestonesManager.get_user_badges` returns highest-tier earned per game/metric.  
- `get_selected_badge` / `set_selected_badge` read/write `user_badge_preferences`.  
- `get_display_badge` returns the emoji for the selected or top badge (with guild emoji resolution).

---

## Tier-based milestone XP

When a milestone doesn’t define `xp`, `_calculate_milestone_xp(milestone, all_milestones)` in `managers/milestones.py` computes 400–700 XP by tier (position in sorted-by-threshold list). Single milestone defaults to 550.

---

## References

- Config: `levels.json`, `leveling.json`, `milestones.json` — [Configuration](CONFIGURATION.md).  
- Commands: `/level`, `/milestones`, `/daily`, `/add-xp` — [Commands & cogs](COMMANDS_AND_COGS.md).  
- Database tables: `leveling`, `xp_logs`, `user_achievements`, `user_badge_preferences` — [Architecture](ARCHITECTURE.md#database).
