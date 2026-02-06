"""
Utility functions for managing game state persistence across bot restarts.
"""
import json
from typing import Dict, Any, Optional
from core.database.pool import DatabasePool
from core.logging.setup import get_logger

logger = get_logger("GameState")


async def save_game_state(game_type: str, game_id: int, user_id: int, state: Dict[str, Any], test_mode: bool = False) -> bool:
    """
    Save game state to database.
    
    Args:
        game_type: Type of game ('2048', 'tictactoe', 'connectfour', 'memory', 'minesweeper')
        game_id: Game ID
        user_id: User ID
        state: Game state dictionary
        test_mode: Whether this is a test game
    
    Returns:
        True if successful, False otherwise
    """
    if test_mode or game_id == -999999:
        return False  # Don't save test games
    
    try:
        db = await DatabasePool.get_instance()
        state_json = json.dumps(state)
        
        # Map game type to table name
        table_map = {
            '2048': 'users_2048',
            'tictactoe': 'users_tictactoe',
            'connectfour': 'users_connectfour',
            'memory': 'users_memory',
            'minesweeper': 'users_minesweeper',
            'hangman': 'users_hangman'
        }
        
        table_name = table_map.get(game_type.lower())
        if not table_name:
            logger.error(f"Unknown game type: {game_type}")
            return False
        
        # Update game_state column
        await db.execute(
            f"UPDATE {table_name} SET game_state = %s WHERE game_id = %s AND user_id = %s",
            (state_json, game_id, user_id)
        )
        
        return True
    except Exception as e:
        logger.error(f"Error saving game state for {game_type} game {game_id}, user {user_id}: {e}")
        return False


async def load_game_state(game_type: str, game_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    """
    Load game state from database.
    
    Args:
        game_type: Type of game
        game_id: Game ID
        user_id: User ID
    
    Returns:
        Game state dictionary, or None if not found
    """
    try:
        db = await DatabasePool.get_instance()
        
        # Map game type to table name
        table_map = {
            '2048': 'users_2048',
            'tictactoe': 'users_tictactoe',
            'connectfour': 'users_connectfour',
            'memory': 'users_memory',
            'minesweeper': 'users_minesweeper',
            'hangman': 'users_hangman'
        }
        
        table_name = table_map.get(game_type.lower())
        if not table_name:
            logger.error(f"Unknown game type: {game_type}")
            return None
        
        # Query game_state column
        result = await db.execute(
            f"SELECT game_state FROM {table_name} WHERE game_id = %s AND user_id = %s",
            (game_id, user_id)
        )
        
        if result and len(result) > 0:
            state_json = result[0].get('game_state')
            if state_json:
                return json.loads(state_json)
        
        return None
    except Exception as e:
        logger.error(f"Error loading game state for {game_type} game {game_id}, user {user_id}: {e}")
        return None


async def get_active_dm_games() -> list:
    """
    Get all active DM games from database.
    
    Returns:
        List of active game records
    """
    try:
        db = await DatabasePool.get_instance()
        
        # Get active games for each DM game type
        active_games = []
        
        game_tables = [
            ('2048', 'users_2048', 'status'),
            ('tictactoe', 'users_tictactoe', 'won'),
            ('connectfour', 'users_connectfour', 'status'),
            ('memory', 'users_memory', 'won'),
            ('minesweeper', 'users_minesweeper', 'won'),
            ('hangman', 'users_hangman', 'won')
        ]
        
        for game_type, table_name, status_column in game_tables:
            try:
                # Get active games (status='Started' or won='Started')
                if status_column == 'won':
                    query = f"SELECT game_id, user_id, {status_column} as status FROM {table_name} WHERE {status_column} = 'Started' AND ended_at = 0"
                else:
                    query = f"SELECT game_id, user_id, {status_column} as status FROM {table_name} WHERE {status_column} = 'Started' AND ended_at = 0"
                
                games = await db.execute(query)
                for game in games:
                    game['game_type'] = game_type
                    active_games.append(game)
            except Exception as e:
                logger.error(f"Error querying active {game_type} games: {e}")
                continue
        
        return active_games
    except Exception as e:
        logger.error(f"Error getting active DM games: {e}")
        return []

