# Configuration Guide

This guide explains the new optimized configuration structure for the Minecadia Games Bot.

## File Structure

```
assets/Configs/
├── bot.json              # Core bot settings (token, database, embed colors)
├── discord.json          # Discord server settings (guild, channels, roles)
├── leveling.json         # Leveling system (XP requirements per level)
├── rewards.json          # Reward templates for monthly winners
├── games/
│   ├── chat.json        # General chat game settings
│   ├── dm.json          # General DM game settings
│   ├── unscramble.json  # Unscramble game words
│   ├── math_quiz.json   # Math quiz problem types
│   ├── trivia.json      # Trivia questions
│   └── flag_guesser.json # Flag guesser API settings
└── data/
    ├── words.txt        # Wordle word list
    └── winners_history.json # Historical winner data
```

## Configuration Files

### `bot.json`
Core bot configuration:
- `token`: Bot token (DO NOT EDIT IN PRODUCTION)
- `presence`: Bot presence text
- `database`: Database connection settings
- `embed`: Embed appearance settings (color, footer, logo)

### `discord.json`
Discord server configuration:
- `guild_id`: Main server ID
- `channels`: Channel IDs (leveling, admin_logs, etc.)
- `roles`: Role IDs (games_notification, verified, winner)
- `permissions`: Admin and staff role names

### `games/chat.json`
Chat game general settings:
- `enabled`: Enable/disable chat games
- `delay`: Min/max seconds between games
- `game_duration`: How long each game lasts (seconds)
- `max_winners`: Maximum number of winners
- `xp`: XP configuration (base + position bonuses)
- `channels`: Channel configuration with weights

### `games/dm.json`
DM game general settings:
- `enabled`: Enable/disable DM games
- `rotation_delay`: How long each DM game is active (seconds)
- `button_cooldown`: Cooldown between button clicks
- `games`: Individual game configurations

### `games/unscramble.json`
Unscramble game:
- `assets`: Image and font paths
- `words`: Words organized by channel ID

### `games/math_quiz.json`
Math quiz game:
- `problem_types`: List of math problem types with IDs

### `games/trivia.json`
Trivia game:
- `questions`: Questions organized by channel ID

### `games/flag_guesser.json`
Flag guesser game:
- `api`: API URL and headers
- `exclude_patterns`: Patterns to exclude (e.g., US states)

### `leveling.json`
Leveling system:
- `levels`: XP required for each level (level number -> XP amount)

### `rewards.json`
Reward templates:
- `message_format`: Format for winner announcements
- `rewards`: Reward descriptions for each position

## Editing via Discord

Use these commands to edit configurations:

- `/config-get <config_file> <key>` - View a config value
- `/config-set <config_file> <key> <value>` - Set a config value (JSON format)
- `/config-reload <config_file>` - Reload a config file

### Examples

```
/config-get games/chat delay
/config-set games/chat delay.min_seconds 1200
/config-set games/dm games.TicTacToe.enabled false
/config-reload games/chat
```

## Backward Compatibility

The config system maintains backward compatibility with old config names:
- `config` → `bot` + `discord`
- `chat_games` → `games/chat`
- `dm_games` → `games/dm`
- `levels` → `leveling`
- `winners` → `rewards`

Old config keys are automatically mapped to new structure.

## Best Practices

1. **Use descriptive names**: Config keys should be self-explanatory
2. **Group related settings**: Keep related configs together
3. **Add comments**: Use `_comment` fields to document settings
4. **Validate values**: The bot validates configs on load
5. **Backup before editing**: Always backup configs before major changes

