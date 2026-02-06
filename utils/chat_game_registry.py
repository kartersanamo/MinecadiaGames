"""
Registry for tracking active chat games and their state.
Allows context menu commands to access and manipulate game state.
"""
from typing import Dict, Optional, List, Any
from datetime import datetime, timezone
import discord


class ChatGameRegistry:
    """Singleton registry for tracking active chat games"""
    _instance: Optional['ChatGameRegistry'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        
        # Store game data by message_id
        # Format: {message_id: {
        #   'game_type': str,
        #   'game_id': int,
        #   'view': discord.ui.View,
        #   'original_state': dict,
        #   'current_state': dict,
        #   'activity_log': List[dict],
        #   'xp_multiplier': float,
        #   'test_mode': bool
        # }}
        self._games: Dict[int, Dict[str, Any]] = {}
        self._initialized = True
    
    def register_game(
        self,
        message_id: int,
        game_type: str,
        game_id: int,
        view: discord.ui.View,
        original_state: Dict[str, Any],
        xp_multiplier: float = 1.0,
        test_mode: bool = False
    ):
        """Register a new chat game"""
        self._games[message_id] = {
            'game_type': game_type,
            'game_id': game_id,
            'view': view,
            'original_state': original_state.copy(),
            'current_state': original_state.copy(),
            'activity_log': [],
            'xp_multiplier': xp_multiplier,
            'test_mode': test_mode,
            'started_at': datetime.now(timezone.utc).timestamp()
        }
    
    def get_game(self, message_id: int) -> Optional[Dict[str, Any]]:
        """Get game data by message ID"""
        return self._games.get(message_id)
    
    def log_activity(
        self,
        message_id: int,
        user_id: int,
        action: str,
        details: Optional[str] = None,
        success: bool = True
    ):
        """Log an activity for a game"""
        if message_id not in self._games:
            return
        
        self._games[message_id]['activity_log'].append({
            'timestamp': datetime.now(timezone.utc).timestamp(),
            'user_id': user_id,
            'action': action,  # 'click', 'wrong_answer', 'correct_answer', 'denied', etc.
            'details': details,
            'success': success
        })
    
    def update_xp_multiplier(self, message_id: int, new_multiplier: float):
        """Update XP multiplier for a game"""
        if message_id in self._games:
            self._games[message_id]['xp_multiplier'] = new_multiplier
    
    def unregister_game(self, message_id: int):
        """Remove game from registry (when game ends)"""
        if message_id in self._games:
            del self._games[message_id]
    
    def get_activity_log(self, message_id: int) -> List[Dict[str, Any]]:
        """Get activity log for a game"""
        if message_id in self._games:
            return self._games[message_id].get('activity_log', [])
        return []


# Global instance
registry = ChatGameRegistry()

