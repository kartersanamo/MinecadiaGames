# Minecadia Games Bot

Discord bot for games, leveling, achievements, and leaderboards on Minecadia.

## What it does

- **DM games** — Wordle, Tic-Tac-Toe, Connect Four, Memory, 2048, Minesweeper, Hangman, Filler
- **Chat games** — Trivia, Unscramble, Flag Guesser, Math Quiz, Emoji Quiz, Guess the Number
- **Progression** — XP, levels, daily rewards, milestones, achievements, and counting channel
- **Leaderboards** — monthly wipe, top winners, and statistics
- **Admin** — config management, XP grants, chat game controls, and practice mode

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # add DISCORD_TOKEN, DB_*, optional GAMES_BOT_API_SECRET
python main.py
```

## Config

- `.env` — token, database, API secret
- `assets/configs/` — bot, discord, games, leveling, milestones, rewards, winners

Uses **MySQL** for all game and XP data.
