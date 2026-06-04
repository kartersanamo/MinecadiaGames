import discord
from core.database.pool import DatabasePool
from core.logging.setup import get_logger
from typing import Optional, List, Dict, Any


class LogsView(discord.ui.View):
    def __init__(
        self,
        bot,
        config,
        log_type: str = "all",
        filter_type: str = "none",
        user_id: Optional[int] = None,
        game_id: Optional[int] = None,
        game_type: Optional[str] = None,
        source: Optional[str] = None,
        time_range: str = "24h"
    ):
        super().__init__(timeout=None)
        self.bot = bot
        self.config = config
        self.logger = get_logger("Commands")
        self.log_type = log_type
        self.filter_type = filter_type
        self.user_id = user_id
        self.game_id = game_id
        self.game_type = game_type
        self.source = source
        self.time_range = time_range
        
        from ui.views.logs_filter_select_view import LogsFilterSelect

        self.add_item(LogsFilterSelect(self))
    
    def _get_time_filter(self) -> Optional[int]:
        """Get timestamp for time range filter"""
        from datetime import datetime, timedelta, timezone
        
        now = datetime.now(timezone.utc)
        
        if self.time_range == "1h":
            return int((now - timedelta(hours=1)).timestamp())
        elif self.time_range == "6h":
            return int((now - timedelta(hours=6)).timestamp())
        elif self.time_range == "24h":
            return int((now - timedelta(hours=24)).timestamp())
        elif self.time_range == "7d":
            return int((now - timedelta(days=7)).timestamp())
        elif self.time_range == "30d":
            return int((now - timedelta(days=30)).timestamp())
        else:
            return None
    
    async def get_logs(self) -> List[Dict[str, Any]]:
        """Get logs based on current filters"""
        try:
            db = await DatabasePool.get_instance()
            logs = []
            time_filter = self._get_time_filter()
            
            if self.log_type == "suspicious":
                return await self._get_suspicious_logs(time_filter)
            
            # Get XP logs
            if self.log_type in ["all", "xp"]:
                try:
                    xp_logs = await self._get_xp_logs(db, time_filter)
                    logs.extend(xp_logs)
                except Exception as e:
                    self.logger.error(f"Error getting XP logs: {e}")
                    import traceback
                    self.logger.error(traceback.format_exc())
            
            # Get game logs (DM game player entries)
            if self.log_type in ["all", "games"]:
                try:
                    game_logs = await self._get_game_logs(db, time_filter)
                    logs.extend(game_logs)
                except Exception as e:
                    self.logger.error(f"Error getting game logs: {e}")
                    import traceback
                    self.logger.error(traceback.format_exc())
                
                # Also get chat game creation events (for "Game Logs Only")
                if self.log_type == "games":
                    try:
                        chat_game_events = await self._get_chat_game_events(db, time_filter)
                        logs.extend(chat_game_events)
                    except Exception as e:
                        self.logger.error(f"Error getting chat game events: {e}")
                        import traceback
                        self.logger.error(traceback.format_exc())
            
            # Get game creation/refresh events (for "All Logs" only)
            if self.log_type == "all":
                try:
                    game_events = await self._get_game_events(db, time_filter)
                    logs.extend(game_events)
                except Exception as e:
                    self.logger.error(f"Error getting game events: {e}")
                    import traceback
                    self.logger.error(traceback.format_exc())
            
            # Sort by timestamp (newest first) and limit to 500 total
            # Handle both string and int timestamps
            def get_timestamp(log):
                ts = log.get('timestamp', 0)
                if isinstance(ts, str):
                    try:
                        return int(ts)
                    except (ValueError, TypeError):
                        return 0
                return int(ts) if ts else 0
            
            logs.sort(key=get_timestamp, reverse=True)
            logs = logs[:500]  # Limit to 500 logs to prevent timeout
            
            return logs
        except Exception as e:
            self.logger.error(f"Error in get_logs: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return []
    
    async def _get_xp_logs(self, db: DatabasePool, time_filter: Optional[int]) -> List[Dict[str, Any]]:
        """Get XP logs with filters"""
        query = """
            SELECT 
                xl.game_id,
                xl.user_id,
                xl.xp,
                xl.channel_id,
                xl.source,
                COALESCE(xl.timestamp, g.refreshed_at) as timestamp,
                g.game_name,
                g.dm_game
            FROM xp_logs xl
            LEFT JOIN games g ON xl.game_id = g.game_id
            WHERE 1=1
        """
        params = []
        
        if self.user_id:
            query += " AND xl.user_id = %s"
            params.append(str(self.user_id))
        
        if self.game_id:
            query += " AND xl.game_id = %s"
            params.append(self.game_id)
        
        if self.source:
            query += " AND xl.source = %s"
            params.append(self.source)
        
        if time_filter:
            query += " AND COALESCE(xl.timestamp, g.refreshed_at) >= %s"
            params.append(time_filter)
        
        query += " ORDER BY COALESCE(xl.timestamp, g.refreshed_at) DESC LIMIT 500"
        
        rows = await db.execute(query, tuple(params) if params else None)
        
        logs = []
        for row in rows:
            logs.append({
                'type': 'xp',
                'game_id': row['game_id'],
                'user_id': int(row['user_id']),
                'xp': row['xp'],
                'channel_id': row['channel_id'],
                'source': row['source'],
                'timestamp': row['timestamp'],
                'game_name': row.get('game_name'),
                'dm_game': row.get('dm_game', False)
            })
        
        return logs
    
    async def _get_game_logs(self, db: DatabasePool, time_filter: Optional[int]) -> List[Dict[str, Any]]:
        """Get game logs from DM game tables"""
        dm_game_tables = {
            'tictactoe': 'users_tictactoe',
            'wordle': 'users_wordle',
            'connectfour': 'users_connectfour',
            'memory': 'users_memory',
            '2048': 'users_2048',
            'minesweeper': 'users_minesweeper',
            'hangman': 'users_hangman'
        }
        
        all_logs = []
        
        # Limit to 100 per table to avoid timeout
        limit_per_table = 100
        
        for game_name, table_name in dm_game_tables.items():
            # Skip if filtering by game type and it doesn't match
            if self.game_type and game_name.lower() != self.game_type.lower():
                continue
            
            # Build query with proper field selection based on table structure
            # Each table has different columns, so we need to handle them separately
            if game_name == 'connectfour':
                query = f"""
                    SELECT 
                        u.game_id,
                        u.user_id,
                        u.status,
                        NULL as score,
                        u.started_at,
                        u.ended_at,
                        u.moves,
                        NULL as highest_tile,
                        g.game_name,
                        g.refreshed_at,
                        g.dm_game
                """
            elif game_name == 'memory':
                query = f"""
                    SELECT 
                        u.game_id,
                        u.user_id,
                        u.won as status,
                        NULL as score,
                        u.started_at,
                        u.ended_at,
                        u.attempts as moves,
                        NULL as highest_tile,
                        g.game_name,
                        g.refreshed_at,
                        g.dm_game
                """
            elif game_name == '2048':
                query = f"""
                    SELECT 
                        u.game_id,
                        u.user_id,
                        u.status,
                        u.score,
                        u.started_at,
                        u.ended_at,
                        u.moves,
                        u.highest_tile,
                        g.game_name,
                        g.refreshed_at,
                        g.dm_game
                """
            elif game_name == 'wordle':
                query = f"""
                    SELECT 
                        u.game_id,
                        u.user_id,
                        u.won as status,
                        NULL as score,
                        u.started_at,
                        u.ended_at,
                        u.attempts as moves,
                        NULL as highest_tile,
                        g.game_name,
                        g.refreshed_at,
                        g.dm_game
                """
            elif game_name == 'minesweeper':
                query = f"""
                    SELECT 
                        u.game_id,
                        u.user_id,
                        u.won as status,
                        NULL as score,
                        u.started_at,
                        u.ended_at,
                        u.cells_revealed as moves,
                        NULL as highest_tile,
                        g.game_name,
                        g.refreshed_at,
                        g.dm_game
                """
            else:  # tictactoe
                query = f"""
                    SELECT 
                        u.game_id,
                        u.user_id,
                        u.won as status,
                        NULL as score,
                        u.started_at,
                        u.ended_at,
                        NULL as moves,
                        NULL as highest_tile,
                        g.game_name,
                        g.refreshed_at,
                        g.dm_game
                """
            
            # Complete the query
            query += f"""
                FROM {table_name} u
                INNER JOIN games g ON u.game_id = g.game_id
                WHERE 1=1
            """
            params = []
            
            if self.user_id:
                query += " AND u.user_id = %s"
                params.append(str(self.user_id))
            
            if self.game_id:
                query += " AND u.game_id = %s"
                params.append(self.game_id)
            
            if time_filter:
                query += " AND u.started_at >= %s"
                params.append(time_filter)
            
            query += f" ORDER BY u.started_at DESC LIMIT {limit_per_table}"
            
            try:
                rows = await db.execute(query, tuple(params) if params else None)
                
                for row in rows:
                    # Get additional game-specific fields
                    moves = row.get('moves')
                    highest_tile = row.get('highest_tile')
                    
                    all_logs.append({
                        'type': 'game',
                        'game_id': row['game_id'],
                        'user_id': int(row['user_id']),
                        'game_name': game_name.title(),
                        'status': row['status'],
                        'score': row.get('score'),
                        'moves': moves,
                        'highest_tile': highest_tile,
                        'started_at': row['started_at'],
                        'ended_at': row.get('ended_at', 0),
                        'timestamp': row['started_at'],
                        'dm_game': True
                    })
            except Exception as e:
                self.logger.error(f"Error fetching logs from {table_name}: {e}")
                import traceback
                self.logger.error(traceback.format_exc())
                continue
        
        return all_logs
    
    async def _get_game_events(self, db: DatabasePool, time_filter: Optional[int]) -> List[Dict[str, Any]]:
        """Get game creation/refresh events from games table"""
        query = """
            SELECT 
                game_id,
                game_name,
                refreshed_at,
                dm_game
            FROM games
            WHERE 1=1
        """
        params = []
        
        if time_filter:
            query += " AND refreshed_at >= %s"
            params.append(time_filter)
        
        query += " ORDER BY refreshed_at DESC LIMIT 200"
        
        rows = await db.execute(query, tuple(params) if params else None)
        
        events = []
        for row in rows:
            event_type = "DM Game Refreshed" if row['dm_game'] else "Chat Game Started"
            events.append({
                'type': 'game_event',
                'game_id': row['game_id'],
                'game_name': row['game_name'],
                'event_type': event_type,
                'timestamp': row['refreshed_at'],
                'dm_game': row['dm_game']
            })
        
        return events
    
    async def _get_chat_game_events(self, db: DatabasePool, time_filter: Optional[int]) -> List[Dict[str, Any]]:
        """Get chat game creation events for Game Logs Only"""
        query = """
            SELECT 
                game_id,
                game_name,
                refreshed_at,
                dm_game
            FROM games
            WHERE dm_game = FALSE
        """
        params = []
        
        if time_filter:
            query += " AND refreshed_at >= %s"
            params.append(time_filter)
        
        query += " ORDER BY refreshed_at DESC LIMIT 200"
        
        rows = await db.execute(query, tuple(params) if params else None)
        
        events = []
        for row in rows:
            events.append({
                'type': 'game',
                'game_id': row['game_id'],
                'game_name': row['game_name'],
                'status': 'Started',
                'score': None,
                'moves': None,
                'highest_tile': None,
                'started_at': row['refreshed_at'],
                'ended_at': 0,
                'timestamp': row['refreshed_at'],
                'dm_game': False,
                'user_id': None  # Chat games don't have a single user
            })
        
        return events
    
    async def _get_suspicious_logs(self, time_filter: Optional[int]) -> List[Dict[str, Any]]:
        """Detect suspicious activity patterns"""
        db = await DatabasePool.get_instance()
        suspicious = []
        
        # 1. Large XP gains in short time
        query = """
            SELECT 
                user_id,
                SUM(xp) as total_xp,
                COUNT(*) as count,
                MIN(COALESCE(xl.timestamp, g.refreshed_at)) as first_time,
                MAX(COALESCE(xl.timestamp, g.refreshed_at)) as last_time,
                MAX(COALESCE(xl.timestamp, g.refreshed_at)) - MIN(COALESCE(xl.timestamp, g.refreshed_at)) as time_span
            FROM xp_logs xl
            LEFT JOIN games g ON xl.game_id = g.game_id
            WHERE 1=1
        """
        params = []
        
        if time_filter:
            query += " AND COALESCE(xl.timestamp, g.refreshed_at) >= %s"
            params.append(time_filter)
        
        query += """
            GROUP BY user_id
            HAVING total_xp > 500 AND time_span < 3600 AND count > 10
            ORDER BY total_xp DESC
            LIMIT 50
        """
        
        rows = await db.execute(query, tuple(params) if params else None)
        
        for row in rows:
            suspicious.append({
                'type': 'suspicious',
                'reason': 'large_xp_short_time',
                'user_id': int(row['user_id']),
                'total_xp': row['total_xp'],
                'count': row['count'],
                'time_span': row['time_span'],
                'timestamp': row['last_time']
            })
        
        # 2. Large single XP gains
        query2 = """
            SELECT 
                xl.game_id,
                xl.user_id,
                xl.xp,
                xl.source,
                COALESCE(xl.timestamp, g.refreshed_at) as timestamp,
                g.game_name
            FROM xp_logs xl
            LEFT JOIN games g ON xl.game_id = g.game_id
            WHERE xl.xp > 100
        """
        params2 = []
        
        if time_filter:
            query2 += " AND COALESCE(xl.timestamp, g.refreshed_at) >= %s"
            params2.append(time_filter)
        
        query2 += " ORDER BY xl.xp DESC LIMIT 50"
        
        rows2 = await db.execute(query2, tuple(params2) if params2 else None)
        
        for row in rows2:
            suspicious.append({
                'type': 'suspicious',
                'reason': 'large_single_xp',
                'game_id': row['game_id'],
                'user_id': int(row['user_id']),
                'xp': row['xp'],
                'source': row['source'],
                'game_name': row.get('game_name'),
                'timestamp': row['timestamp']
            })
        
        # 3. Unusual patterns (same user, same game, many wins quickly)
        query3 = """
            SELECT 
                xl.user_id,
                xl.source,
                COUNT(*) as count,
                SUM(xl.xp) as total_xp,
                MAX(COALESCE(xl.timestamp, g.refreshed_at)) as last_time
            FROM xp_logs xl
            LEFT JOIN games g ON xl.game_id = g.game_id
            WHERE 1=1
        """
        params3 = []
        
        if time_filter:
            query3 += " AND COALESCE(xl.timestamp, g.refreshed_at) >= %s"
            params3.append(time_filter)
        
        query3 += """
            GROUP BY xl.user_id, xl.source
            HAVING count > 20 AND total_xp > 300
            ORDER BY count DESC
            LIMIT 30
        """
        
        rows3 = await db.execute(query3, tuple(params3) if params3 else None)
        
        for row in rows3:
            suspicious.append({
                'type': 'suspicious',
                'reason': 'unusual_pattern',
                'user_id': int(row['user_id']),
                'source': row['source'],
                'count': row['count'],
                'total_xp': row['total_xp'],
                'timestamp': row['last_time']
            })
        
        # Sort by timestamp
        suspicious.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
        
        return suspicious
