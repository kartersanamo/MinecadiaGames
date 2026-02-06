import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
from threading import Lock


class ConfigManager:
    _instance: Optional['ConfigManager'] = None
    _lock = Lock()
    
    def __init__(self, config_dir: str = None):
        if config_dir is None:
            from pathlib import Path
            config_dir = str(Path(__file__).parent.parent.parent / "assets" / "Configs")
        self.config_dir = Path(config_dir)
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._file_locks: Dict[str, Lock] = {}
        self._ensure_config_dir()
    
    def _ensure_config_dir(self):
        self.config_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_file_lock(self, filename: str) -> Lock:
        if filename not in self._file_locks:
            self._file_locks[filename] = Lock()
        return self._file_locks[filename]
    
    def get(self, config_name: str, key: Optional[str] = None, default: Any = None) -> Any:
        # Validate inputs
        if not isinstance(config_name, str):
            raise TypeError(f"config_name must be a string, got {type(config_name).__name__}: {config_name}")
        
        # Handle case where second argument is a default value (not a key)
        # This allows calls like: config.get('name', {}) where {} is the default, not the key
        if key is not None and not isinstance(key, str):
            # Second argument is not a string, so it must be the default value
            default = key
            key = None
        
        if key is not None and not isinstance(key, str):
            raise TypeError(f"key must be a string or None, got {type(key).__name__}: {key}")
        
        # Map old config names to new structure for backward compatibility
        config_mapping = {
            'config': 'bot',  # Main config -> bot.json + discord.json
            'chat_games': 'games/chat',  # Chat games -> games/chat.json
            'dm_games': 'games/dm',  # DM games -> games/dm.json
            'levels': 'leveling',  # Levels -> leveling.json
            'winners': 'rewards',  # Winners -> rewards.json
            'tictactoe': 'games/dm',  # Individual game configs are in games/dm.json
            'memory': 'games/dm',
            'wordle': 'games/dm',
            'connect_four': 'games/dm',
            'flag_guesser': 'games/flag_guesser',
            'math_quiz': 'games/math_quiz',
            'trivia': 'games/trivia',
            'unscramble': 'games/unscramble',
            'emoji_quiz': 'games/emoji_quiz'
        }
        
        # Use mapped name if exists, otherwise use original
        mapped_name = config_mapping.get(config_name, config_name)
        
        if mapped_name in self._cache:
            config = self._cache[mapped_name]
        else:
            config = self._load_config(mapped_name)
            self._cache[mapped_name] = config
        
        # Special handling for 'config' - merge bot.json and discord.json
        if config_name == 'config':
            if 'bot' not in self._cache:
                self._cache['bot'] = self._load_config('bot')
            if 'discord' not in self._cache:
                self._cache['discord'] = self._load_config('discord')
            
            bot_config = self._cache['bot']
            discord_config = self._cache['discord']
            
            # Merge configs for backward compatibility
            merged_config = {
                **bot_config,
                **discord_config,
                'permissions': discord_config.get('permissions', {}),
                'channels': discord_config.get('channels', {}),
                'roles': discord_config.get('roles', {})
            }
            config = merged_config
        
        # Handle key mapping for backward compatibility
        if config_name == 'config' and key:
            key_mapping = {
                'TOKEN': 'token',
                'PRESENCE': 'presence',
                'DATABASE_CONFIG': 'database',
                'ADMIN_ROLES': 'permissions.admin_roles',
                'STAFF_ROLES': 'permissions.staff_roles',
                'EMBED_COLOR': 'embed.color',
                'FOOTER': 'embed.footer',
                'LOGO': 'embed.logo',
                'GUILD_ID': 'guild_id',
                'GAMES_ROLE': 'roles.games_notification',
                'VERIFIED_ROLE': 'roles.verified',
                'ADMIN_LOGS': 'channels.admin_logs',
                'LOGS_CHANNEL': 'channels.logs',
                'DISCORD_TICKETS': 'channels.tickets_category',
                'ANNOUNCE_CHANNELS': 'channels.announce'
            }
            if key in key_mapping:
                key = key_mapping[key]
        
        if config_name == 'chat_games' and key:
            # Map old chat_games keys to new structure
            if key == 'DELAY':
                # Return delay dict with LOWER/UPPER mapped to min_seconds/max_seconds
                delay_config = config.get('delay', {})
                return {
                    'LOWER': delay_config.get('min_seconds', 1500),
                    'UPPER': delay_config.get('max_seconds', 2100)
                }
            elif key == 'CHANNELS':
                # Map channels structure
                channels = config.get('channels', {})
                mapped_channels = {}
                for name, ch_data in channels.items():
                    mapped_channels[name] = {
                        'CHANNEL_ID': ch_data.get('id'),
                        'CHANCE': ch_data.get('weight', 0.0)
                    }
                return mapped_channels
            elif key == 'WINNERS':
                return config.get('max_winners', 3)
            elif key == 'GAME_LENGTH':
                return config.get('game_duration', 600)
            elif key == 'XP':
                xp_config = config.get('xp', {})
                return {
                    'XP_ADD': xp_config.get('base', 10),
                    'XP_LOWER': xp_config.get('positions', {})
                }
            elif key == 'GAMES':
                # Return game-specific configs
                games = {}
                # Unscramble
                unscramble_config = self._load_config('games/unscramble')
                games['Unscramble'] = unscramble_config
                # Math Quiz
                math_config = self._load_config('games/math_quiz')
                games['Math Quiz'] = {'QUESTIONS': math_config.get('problem_types', [])}
                # Flag Guesser
                flag_config = self._load_config('games/flag_guesser')
                games['Flag Guesser'] = {
                    'API_URL': flag_config.get('api', {}).get('url'),
                    'REQUEST_HEADERS': flag_config.get('api', {}).get('headers', {})
                }
                # Trivia
                trivia_config = self._load_config('games/trivia')
                games['Trivia'] = {'QUESTIONS': trivia_config.get('questions', {})}
                return games
        
        if config_name == 'dm_games' and key:
            if key == 'DELAY':
                return config.get('rotation_delay', 7200)
            elif key == 'BUTTON_COOLDOWN':
                return config.get('button_cooldown', 0.8)
            elif key == 'GAMES':
                return config.get('games', {})
            elif key and key.startswith('GAMES.'):
                # Handle GAMES.TicTacToe.IMAGE etc.
                parts = key.split('.')
                if len(parts) >= 2:
                    game_name = parts[1]
                    games = config.get('games', {})
                    game_config = games.get(game_name, {})
                    if len(parts) > 2:
                        # Navigate nested keys
                        prop = '.'.join(parts[2:])
                        keys = prop.split('.')
                        value = game_config
                        for k in keys:
                            if isinstance(value, dict):
                                value = value.get(k)
                                if value is None:
                                    return default
                            else:
                                return default
                        return value if value is not None else default
                    return game_config
        
        if config_name == 'levels' and key:
            if key == 'LEVELS':
                key = 'levels'
        
        if key is None:
            return config
        
        # Ensure key is a string before calling split
        if not isinstance(key, str):
            raise TypeError(f"Config key must be a string, got {type(key).__name__}: {key}")
        
        keys = key.split('.')
        value = config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default
        return value if value is not None else default
    
    def set(self, config_name: str, key: str, value: Any) -> bool:
        config = self.get(config_name)
        keys = key.split('.')
        
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        config[keys[-1]] = value
        return self._save_config(config_name, self._cache[config_name])
    
    def _load_config(self, config_name: str) -> Dict[str, Any]:
        # Handle subdirectory paths (e.g., "games/chat")
        if '/' in config_name:
            file_path = self.config_dir / f"{config_name}.json"
        else:
            file_path = self.config_dir / f"{config_name}.json"
        
        lock = self._get_file_lock(config_name)
        
        with lock:
            if not file_path.exists():
                return {}
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                raise ValueError(f"Failed to load config {config_name}: {e}")
    
    def _save_config(self, config_name: str, config: Dict[str, Any]) -> bool:
        # Handle subdirectory paths
        if '/' in config_name:
            file_path = self.config_dir / f"{config_name}.json"
            # Ensure parent directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            file_path = self.config_dir / f"{config_name}.json"
        
        lock = self._get_file_lock(config_name)
        
        with lock:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=4, ensure_ascii=False)
                return True
            except IOError as e:
                raise ValueError(f"Failed to save config {config_name}: {e}")
    
    def reload(self, config_name: Optional[str] = None):
        if config_name:
            if config_name in self._cache:
                del self._cache[config_name]
        else:
            self._cache.clear()
    
    @classmethod
    def get_instance(cls) -> 'ConfigManager':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

