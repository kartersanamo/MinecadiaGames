from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional

from ui.paginator import Paginator

if TYPE_CHECKING:
    from ui.views.logs_view import LogsView


class LogsPaginator(Paginator):
    def __init__(self, parent_view: LogsView, logs_data: List[Dict], log_type: str, game_id: Optional[int] = None, user_id: Optional[int] = None, logs_cog = None):
        super().__init__(timeout=900)
        self.parent_view = parent_view
        self.logs_data = logs_data
        self.log_type = log_type
        self.game_id = game_id
        self.user_id = user_id
        self.logs_cog = logs_cog
        self.title = self._get_title()
        self.data = self._format_logs()
        self.sep = 10
        self.ephemeral = True
        
        # Add quick action buttons
        if game_id:
            view_button = discord.ui.Button(
                label=f"View Game #{game_id}",
                style=discord.ButtonStyle.blurple,
                emoji="🎮",
                custom_id=f"view_game_{game_id}",
                row=1
            )
            view_button.callback = self._create_game_callback(game_id)
            self.add_item(view_button)
        
        if user_id:
            view_user_button = discord.ui.Button(
                label="View User Details",
                style=discord.ButtonStyle.blurple,
                emoji="👤",
                custom_id=f"view_user_{user_id}",
                row=1
            )
            view_user_button.callback = self._create_user_callback(user_id)
            self.add_item(view_user_button)
    
    def _create_game_callback(self, game_id: int):
        async def callback(interaction: discord.Interaction):
            if self.logs_cog:
                await self.logs_cog._show_game_details(interaction, game_id)
        return callback
    
    def _create_user_callback(self, user_id: int):
        async def callback(interaction: discord.Interaction):
            if self.logs_cog:
                await self.logs_cog._show_user_details(interaction, user_id)
        return callback
    
    def _get_title(self) -> str:
        title = "📊 System Logs"
        if self.log_type == "suspicious":
            title = "⚠️ Suspicious Activity Logs"
        elif self.log_type == "xp":
            title = "💰 XP Logs"
        elif self.log_type == "games":
            title = "🎮 Game Logs"
        
        return title
    
    def _format_logs(self) -> List[str]:
        """Format logs for display"""
        formatted = []
        
        for log in self.logs_data:
            if log['type'] == 'xp':
                formatted.append(self._format_xp_log(log))
            elif log['type'] == 'game':
                formatted.append(self._format_game_log(log))
            elif log['type'] == 'game_event':
                formatted.append(self._format_game_event_log(log))
            elif log['type'] == 'suspicious':
                formatted.append(self._format_suspicious_log(log))
            
            # Add spacing between logs (empty line)
            formatted.append("")
        
        # Remove last empty line if exists
        if formatted and formatted[-1] == "":
            formatted.pop()
        
        return formatted
    
    def _format_xp_log(self, log: Dict) -> str:
        """Format an XP log entry"""
        user = self.parent_view.bot.get_user(log['user_id'])
        user_name = user.mention if user else f"<@{log['user_id']}>"
        
        timestamp = log.get('timestamp', 0)
        time_str = f"<t:{timestamp}:R>" if timestamp else "Unknown"
        
        game_info = ""
        if log.get('game_id'):
            game_info = f" | Game #{log['game_id']}"
            if log.get('game_name'):
                game_info += f" ({log['game_name']})"
        
        source = log.get('source', 'Unknown')
        
        return (
            f"**💰 XP Award**\n"
            f"User: {user_name}\n"
            f"XP: `{log['xp']}`\n"
            f"Source: `{source}`{game_info}\n"
            f"Time: {time_str}"
        )
    
    def _format_game_log(self, log: Dict) -> str:
        """Format a game log entry"""
        timestamp = log.get('timestamp', 0)
        time_str = f"<t:{timestamp}:R>" if timestamp else "Unknown"
        
        # Handle chat games (no user_id)
        if log.get('user_id') is None:
            status = log.get('status', 'Started')
            status_emoji = {
                'Finished': '✅',
                'Started': '🟡'
            }.get(status, '❓')
            game_info = f"**🎮 {log.get('game_name', 'Game')} #{log['game_id']}**\n"
            game_info += f"Type: `Chat Game`\n"
            game_info += f"Status: {status_emoji} `{status}`\n"
            game_info += f"Started: {time_str}"
            return game_info
        
        # Handle DM games (with user_id)
        user = self.parent_view.bot.get_user(log['user_id'])
        user_name = user.mention if user else f"<@{log['user_id']}>"
        
        status_emoji = {
            'Won': '✅',
            'Lost': '❌',
            'Started': '🟡',
            'Cashed Out': '💰'
        }.get(log.get('status', ''), '❓')
        
        game_info = f"**🎮 {log.get('game_name', 'Game')} #{log['game_id']}**\n"
        game_info += f"User: {user_name}\n"
        game_info += f"Status: {status_emoji} `{log.get('status', 'Unknown')}`\n"
        
        if log.get('score') is not None:
            game_info += f"Score: `{log['score']}`\n"
        if log.get('moves') is not None:
            game_info += f"Moves: `{log['moves']}`\n"
        if log.get('highest_tile') is not None:
            game_info += f"Highest Tile: `{log['highest_tile']}`\n"
        
        if log.get('ended_at', 0) > 0:
            duration = log['ended_at'] - log.get('started_at', 0)
            game_info += f"Duration: `{duration}s`\n"
        
        game_info += f"Started: {time_str}"
        
        return game_info
    
    def _format_game_event_log(self, log: Dict) -> str:
        """Format a game creation/refresh event log"""
        timestamp = log.get('timestamp', 0)
        time_str = f"<t:{timestamp}:R>" if timestamp else "Unknown"
        
        event_type = log.get('event_type', 'Game Event')
        game_name = log.get('game_name', 'Game')
        game_id = log.get('game_id', 0)
        is_dm = log.get('dm_game', False)
        
        emoji = "🔄" if is_dm else "▶️"
        
        event_info = f"**{emoji} {event_type}**\n"
        event_info += f"Game: `{game_name} #{game_id}`\n"
        event_info += f"Type: `{'DM Game' if is_dm else 'Chat Game'}`\n"
        event_info += f"Time: {time_str}"
        
        return event_info
    
    def _format_suspicious_log(self, log: Dict) -> str:
        """Format a suspicious log entry"""
        user = self.parent_view.bot.get_user(log['user_id'])
        user_name = user.mention if user else f"<@{log['user_id']}>"
        
        timestamp = log.get('timestamp', 0)
        time_str = f"<t:{timestamp}:R>" if timestamp else "Unknown"
        
        reason = log.get('reason', 'unknown')
        reason_text = {
            'large_xp_short_time': 'Large XP gain in short time',
            'large_single_xp': 'Large single XP gain',
            'unusual_pattern': 'Unusual activity pattern'
        }.get(reason, reason)
        
        suspicious_info = f"**⚠️ Suspicious Activity**\n"
        suspicious_info += f"User: {user_name}\n"
        suspicious_info += f"Reason: `{reason_text}`\n"
        
        if 'total_xp' in log:
            suspicious_info += f"Total XP: `{log['total_xp']}`\n"
        if 'count' in log:
            suspicious_info += f"Count: `{log['count']}`\n"
        if 'time_span' in log:
            suspicious_info += f"Time Span: `{log['time_span']}s`\n"
        if 'xp' in log:
            suspicious_info += f"XP: `{log['xp']}`\n"
        if 'source' in log:
            suspicious_info += f"Source: `{log['source']}`\n"
        if 'game_id' in log:
            suspicious_info += f"Game ID: `{log['game_id']}`\n"
        
        suspicious_info += f"Time: {time_str}"
        
        return suspicious_info
