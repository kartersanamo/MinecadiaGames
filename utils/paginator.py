import discord
import re
from typing import List, Optional
from core.config.manager import ConfigManager


LOGO = "Assets/Logo.png"


class Paginator(discord.ui.View):
    def __init__(self, timeout: Optional[float] = None):
        # Use None for persistent views (default)
        super().__init__(timeout=None)
        self.data: List[str] = []
        self.title: str = ""
        self.sep: int = 5
        self.current_page: int = 1
        self.category: Optional[discord.CategoryChannel] = None
        self.count: bool = False
        self.games: Optional[List[str]] = None
        self.ephemeral: bool = False
        self.back_callback: Optional[callable] = None
        self.game_ids: Optional[List[dict]] = None  # Store game_id info for dropdown
    
    async def send(self, interaction: discord.Interaction):
        # Add back button if callback is set
        if self.back_callback:
            self.add_back_button()
        
        if self.ephemeral:
            # For ephemeral, send directly in the response (or followup if already deferred)
            embed = self.create_embed()
            self.update_buttons()
            # Add game selector dropdown if game_ids are available
            if self.game_ids:
                self.add_game_selector()
            try:
                if interaction.response.is_done():
                    msg = await interaction.followup.send(embed=embed, view=self, ephemeral=True)
                else:
                    msg = await interaction.response.send_message(embed=embed, view=self, ephemeral=True)
            except:
                # Fallback to followup if response fails
                msg = await interaction.followup.send(embed=embed, view=self, ephemeral=True)
            return msg
        elif self.games:
            # For games with non-ephemeral, edit the original message
            await interaction.message.edit(view=self, content="")
            await self.update_message(interaction)
        else:
            # Regular non-ephemeral response
            try:
                await interaction.response.send_message(view=self, content="")
            except:
                await interaction.edit_original_response(view=self, content="")
            await self.update_message(interaction)
    
    def create_embed(self) -> discord.Embed:
        config = ConfigManager.get_instance()
        embed = discord.Embed(title=self.title, description="", color=discord.Color.from_str(config.get('config', 'EMBED_COLOR')))
        footer_text = self.get_footer_text()
        
        if self.data and self.data[0] == "No data found.":
            embed.description = "No data found."
        else:
            if self.count:
                for index, item in enumerate(self.get_current_page_data()):
                    embed.description += f"**{(self.sep*self.current_page)-(self.sep-(index+1))}.** {item}\n"
            else:
                for item in self.get_current_page_data():
                    embed.description += f"{item}\n"
        
        if footer_text:
            from utils.helpers import get_embed_logo_url
            logo_url = get_embed_logo_url(LOGO)
            embed.set_footer(icon_url=logo_url, text=footer_text)
        
        return embed
    
    async def update_message(self, interaction: discord.Interaction):
        self.update_buttons()
        embed = self.create_embed()
        
        if self.ephemeral:
            # For ephemeral, edit the original response
            await interaction.edit_original_response(embed=embed, view=self)
        elif self.games:
            # For games with non-ephemeral, edit the original message
            await interaction.message.edit(embeds=[embed], view=self)
        else:
            # Regular non-ephemeral response
            await interaction.edit_original_response(embed=embed, view=self)
    
    def update_buttons(self):
        if not self.data or self.data[0] == "No data found.":
            return
        
        total_pages = (len(self.data) + self.sep - 1) // self.sep
        is_first_page = self.current_page == 1
        is_last_page = self.current_page >= total_pages
        
        self.first_page_button.disabled = is_first_page
        self.prev_button.disabled = is_first_page
        self.first_page_button.style = discord.ButtonStyle.gray if is_first_page else discord.ButtonStyle.red
        self.prev_button.style = discord.ButtonStyle.gray if is_first_page else discord.ButtonStyle.red
        self.next_button.disabled = is_last_page
        self.last_page_button.disabled = is_last_page
        self.last_page_button.style = discord.ButtonStyle.gray if is_last_page else discord.ButtonStyle.red
        self.next_button.style = discord.ButtonStyle.gray if is_last_page else discord.ButtonStyle.red
        
        # Show/hide back button based on whether callback is set
        if hasattr(self, 'back_button'):
            self.back_button.disabled = False
    
    def get_current_page_data(self) -> List[str]:
        until_item = self.current_page * self.sep
        from_item = until_item - self.sep if self.current_page != 1 else 0
        return self.data[from_item:until_item]
    
    def get_footer_text(self) -> str:
        if not self.data or self.data[0] == "No data found.":
            return ""
        
        total_pages = (len(self.data) + self.sep - 1) // self.sep
        return f"Page {self.current_page}/{total_pages} ({len(self.data)} total) | Minecadia Support Bot"
    
    async def handle_page_button(self, interaction: discord.Interaction, step: int):
        await interaction.response.defer(ephemeral=self.ephemeral)
        self.current_page += step
        
        # Update game selector dropdown to show only current page games
        if self.game_ids:
            # Get current page data
            current_page_data = self.get_current_page_data()
            
            # Extract game IDs from current page's formatted strings
            current_page_game_ids = set()
            for item in current_page_data:
                # Extract game_id from format like `#12345`
                match = re.search(r'`#(\d+)`', item)
                if match:
                    current_page_game_ids.add(int(match.group(1)))
            
            # If we have games list, also check there
            if self.games:
                until_item = self.current_page * self.sep
                from_item = until_item - self.sep if self.current_page != 1 else 0
                current_games = self.games[from_item:until_item]
                for game_str in current_games:
                    # Format is: "{game_id} {game_name}"
                    parts = game_str.split(' ', 1)
                    if parts and parts[0].isdigit():
                        current_page_game_ids.add(int(parts[0]))
            
            # Update the game selector dropdown
            for child in self.children:
                if isinstance(child, discord.ui.Select) and child.custom_id == "game_id_selector":
                    # Create a mapping of game_id to game_info for quick lookup
                    game_id_map = {game_info.get('game_id'): game_info for game_info in self.game_ids}
                    
                    # Create new options for current page
                    new_options = []
                    for game_id in sorted(current_page_game_ids, reverse=True)[:25]:  # Discord limit is 25
                        game_info = game_id_map.get(game_id)
                        if not game_info:
                            continue
                        
                        game_name = game_info.get('game_name', 'Unknown')
                        is_dm = game_info.get('dm_game', False)
                        game_type = "DM" if is_dm else "Chat"
                        
                        # Format timestamp for description
                        timestamp = game_info.get('refreshed_at', 0)
                        if timestamp:
                            try:
                                from datetime import datetime
                                timestamp_int = int(timestamp) if isinstance(timestamp, str) else timestamp
                                dt = datetime.fromtimestamp(timestamp_int)
                                time_str = dt.strftime("%m/%d %H:%M")
                            except (ValueError, TypeError, OSError):
                                time_str = "Unknown"
                        else:
                            time_str = "Unknown"
                        
                        label = f"#{game_id} - {game_name} ({game_type})"
                        if len(label) > 100:
                            label = label[:97] + "..."
                        
                        new_options.append(
                            discord.SelectOption(
                                label=label,
                                value=str(game_id),
                                description=f"{time_str} | {game_type} Game"
                            )
                        )
                    
                    child.options = new_options
                    break
        
        if self.games:
            until_item = self.current_page * self.sep
            from_item = until_item - self.sep if self.current_page != 1 else 0
            data = self.games[from_item:until_item]
            for child in self.children:
                if isinstance(child, discord.ui.Select) and child.custom_id == "recent_game_selector":
                    child.options = [discord.SelectOption(label=game) for game in data]
                    break
        
        await self.update_message(interaction)
    
    @discord.ui.button(label="|<", style=discord.ButtonStyle.gray, disabled=True, custom_id="lskip")
    async def first_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_page_button(interaction, 1 - self.current_page)
    
    @discord.ui.button(label="<", style=discord.ButtonStyle.gray, disabled=True, custom_id="left")
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_page_button(interaction, -1)
    
    @discord.ui.button(label=">", style=discord.ButtonStyle.gray, disabled=True, custom_id="right")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_page_button(interaction, 1)
    
    @discord.ui.button(label=">|", style=discord.ButtonStyle.gray, disabled=True, custom_id="rskip")
    async def last_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        total_pages = (len(self.data) + self.sep - 1) // self.sep
        await self.handle_page_button(interaction, total_pages - self.current_page)
    
    def add_back_button(self):
        """Add a back button to the paginator if a back callback is set."""
        if self.back_callback:
            back_button = discord.ui.Button(
                label="← Back",
                style=discord.ButtonStyle.grey,
                custom_id="back_button",
                row=2
            )
            async def back_callback(interaction: discord.Interaction):
                await interaction.response.defer(ephemeral=self.ephemeral)
                await self.back_callback(interaction)
            
            back_button.callback = back_callback
            self.back_button = back_button
            self.add_item(back_button)
    
    def add_game_selector(self):
        """Add a game selector dropdown to the paginator showing only games from current page"""
        if not self.game_ids:
            return
        
        # Remove existing game selector if any
        for child in self.children:
            if isinstance(child, discord.ui.Select) and child.custom_id == "game_id_selector":
                self.remove_item(child)
                break
        
        # Get current page data
        current_page_data = self.get_current_page_data()
        
        # Extract game IDs from current page's formatted strings
        # Format is: `#{game_id}` **{game_name}** <t:{timestamp}:R>
        current_page_game_ids = set()
        for item in current_page_data:
            # Extract game_id from format like `#12345` or from games list format
            match = re.search(r'`#(\d+)`', item)
            if match:
                current_page_game_ids.add(int(match.group(1)))
        
        # If we have games list, also check there
        if self.games:
            until_item = self.current_page * self.sep
            from_item = until_item - self.sep if self.current_page != 1 else 0
            current_games = self.games[from_item:until_item]
            for game_str in current_games:
                # Format is: "{game_id} {game_name}"
                parts = game_str.split(' ', 1)
                if parts and parts[0].isdigit():
                    current_page_game_ids.add(int(parts[0]))
        
        # Create options only for games on current page
        options = []
        # Create a mapping of game_id to game_info for quick lookup
        game_id_map = {game_info.get('game_id'): game_info for game_info in self.game_ids}
        
        # Sort by game_id descending to match the order in the embed
        for game_id in sorted(current_page_game_ids, reverse=True)[:25]:  # Discord limit is 25
            game_info = game_id_map.get(game_id)
            if not game_info:
                continue
            
            game_name = game_info.get('game_name', 'Unknown')
            is_dm = game_info.get('dm_game', False)
            game_type = "DM" if is_dm else "Chat"
            
            # Format timestamp for description
            timestamp = game_info.get('refreshed_at', 0)
            if timestamp:
                try:
                    from datetime import datetime
                    timestamp_int = int(timestamp) if isinstance(timestamp, str) else timestamp
                    dt = datetime.fromtimestamp(timestamp_int)
                    time_str = dt.strftime("%m/%d %H:%M")
                except (ValueError, TypeError, OSError):
                    time_str = "Unknown"
            else:
                time_str = "Unknown"
            
            label = f"#{game_id} - {game_name} ({game_type})"
            if len(label) > 100:
                label = label[:97] + "..."
            
            options.append(
                discord.SelectOption(
                    label=label,
                    value=str(game_id),
                    description=f"{time_str} | {game_type} Game"
                )
            )
        
        if options:
            select = GameIdSelect(self, options)
            self.add_item(select)


class GameIdSelect(discord.ui.Select):
    def __init__(self, parent_view: Paginator, options: list):
        self.parent_view = parent_view
        super().__init__(
            placeholder="Select a game by ID to view details...",
            options=options,
            custom_id="game_id_selector",
            row=4
        )
    
    async def callback(self, interaction: discord.Interaction):
        from managers.game_manager import GameManager
        from core.config.manager import ConfigManager
        from datetime import datetime
        
        game_id = int(self.values[0])
        await interaction.response.defer(ephemeral=True)
        
        # Get game info
        from core.database.pool import DatabasePool
        db = await DatabasePool.get_instance()
        
        game_info = await db.execute(
            "SELECT game_name, refreshed_at, dm_game FROM games WHERE game_id = %s",
            (game_id,)
        )
        
        if not game_info:
            await interaction.followup.send(f"Game #{game_id} not found.", ephemeral=True)
            return
        
        game = game_info[0]
        game_name = game['game_name']
        is_dm_game = game.get('dm_game', False)
        
        # Get all XP logs for this game
        xp_logs = await db.execute(
            """
            SELECT user_id, xp, source, COALESCE(xl.timestamp, g.refreshed_at) as timestamp
            FROM xp_logs xl
            LEFT JOIN games g ON xl.game_id = g.game_id
            WHERE xl.game_id = %s
            ORDER BY COALESCE(xl.timestamp, g.refreshed_at) DESC
            LIMIT 500
            """,
            (game_id,)
        )
        
        # Get game-specific data
        game_data = []
        if is_dm_game:
            game_name_lower = game_name.lower().replace(" ", "")
            table_name = f"users_{game_name_lower}"
            
            try:
                # Different games have different column structures
                if game_name_lower == 'wordle':
                    game_data = await db.execute(
                        f"""
                        SELECT user_id, won as status, NULL as score, started_at, ended_at, attempts as moves
                        FROM {table_name}
                        WHERE game_id = %s
                        ORDER BY started_at DESC
                        """,
                        (game_id,)
                    )
                elif game_name_lower in ['tictactoe', 'connectfour', 'minesweeper']:
                    if game_name_lower == 'minesweeper':
                        game_data = await db.execute(
                            f"""
                            SELECT user_id, won as status, NULL as score, started_at, ended_at, cells_revealed as moves
                            FROM {table_name}
                            WHERE game_id = %s
                            ORDER BY started_at DESC
                            """,
                            (game_id,)
                        )
                    else:
                        game_data = await db.execute(
                            f"""
                            SELECT user_id, won as status, NULL as score, started_at, ended_at, NULL as moves
                            FROM {table_name}
                            WHERE game_id = %s
                            ORDER BY started_at DESC
                            """,
                            (game_id,)
                        )
                elif game_name_lower == 'memory':
                    game_data = await db.execute(
                        f"""
                        SELECT user_id, won as status, NULL as score, started_at, ended_at, attempts as moves
                        FROM {table_name}
                        WHERE game_id = %s
                        ORDER BY started_at DESC
                        """,
                        (game_id,)
                    )
                elif game_name_lower == '2048':
                    game_data = await db.execute(
                        f"""
                        SELECT user_id, status, score, started_at, ended_at, moves
                        FROM {table_name}
                        WHERE game_id = %s
                        ORDER BY started_at DESC
                        """,
                        (game_id,)
                    )
                else:
                    # Fallback: try generic query
                    game_data = await db.execute(
                        f"""
                        SELECT user_id, status, score, started_at, ended_at, moves
                        FROM {table_name}
                        WHERE game_id = %s
                        ORDER BY started_at DESC
                        """,
                        (game_id,)
                    )
            except Exception as e:
                from core.logging.setup import get_logger
                logger = get_logger("Commands")
                logger.error(f"Error fetching game data from {table_name}: {e}")
                pass
        
        # Create comprehensive embed
        config = ConfigManager.get_instance()
        
        # Convert timestamp to int if it's a string
        refreshed_at = game['refreshed_at']
        if isinstance(refreshed_at, str):
            refreshed_at = int(refreshed_at)
        
        embed = discord.Embed(
            title=f"🎮 Game #{game_id} - {game_name}",
            color=discord.Color.from_str(config.get('config', 'EMBED_COLOR')),
            timestamp=datetime.fromtimestamp(refreshed_at)
        )
        
        embed.add_field(
            name="Game Info",
            value=(
                f"**Type:** {'DM Game' if is_dm_game else 'Chat Game'}\n"
                f"**Created:** <t:{game['refreshed_at']}:F>\n"
                f"**Created:** <t:{game['refreshed_at']}:R>"
            ),
            inline=False
        )
        
        # XP Statistics
        if xp_logs:
            total_xp = sum(log['xp'] for log in xp_logs)
            unique_users = len(set(log['user_id'] for log in xp_logs))
            
            embed.add_field(
                name="XP Statistics",
                value=(
                    f"**Total XP Awarded:** {total_xp:,}\n"
                    f"**Unique Players:** {unique_users}\n"
                    f"**Total Awards:** {len(xp_logs)}"
                ),
                inline=False
            )
            
            # Top 10 players
            user_xp = {}
            for log in xp_logs:
                user_id = int(log['user_id'])
                user_xp[user_id] = user_xp.get(user_id, 0) + log['xp']
            
            top_players = sorted(user_xp.items(), key=lambda x: x[1], reverse=True)[:10]
            top_players_text = "\n".join([
                f"{i+1}. <@{user_id}> - {xp:,} XP"
                for i, (user_id, xp) in enumerate(top_players)
            ])
            
            embed.add_field(
                name="Top Players",
                value=top_players_text or "No players",
                inline=False
            )
        
        # DM Game specific info
        if is_dm_game and game_data:
            status_counts = {}
            total_players = len(game_data)
            completed = sum(1 for d in game_data if d.get('ended_at', 0) > 0)
            
            for data in game_data:
                status = data.get('status', 'Unknown')
                status_counts[status] = status_counts.get(status, 0) + 1
            
            status_text = "\n".join([
                f"**{status}:** {count}"
                for status, count in status_counts.items()
            ])
            
            embed.add_field(
                name="Game Statuses",
                value=(
                    f"**Total Players:** {total_players}\n"
                    f"**Completed:** {completed}\n"
                    f"**In Progress:** {total_players - completed}\n\n"
                    f"{status_text}"
                ),
                inline=True
            )
            
            # All players list
            players_text = "\n".join([
                f"<@{int(p['user_id'])}> - {p.get('status', 'Unknown')}"
                for p in game_data[:50]  # Limit to 50 for embed
            ])
            
            if len(game_data) > 50:
                players_text += f"\n... and {len(game_data) - 50} more players"
            
            embed.add_field(
                name="All Players",
                value=players_text or "No players",
                inline=False
            )
        
        from utils.helpers import get_embed_logo_url
        logo_url = get_embed_logo_url(config.get('config', 'LOGO'))
        embed.set_footer(text=config.get('config', 'FOOTER'), icon_url=logo_url)
        
        # Try to get game_manager from paginator first, then from client
        game_manager = getattr(self.parent_view, 'game_manager', None)
        # Check if game_manager was stored on paginator (indicates it's from /game-manager)
        is_from_game_manager = game_manager is not None
        if not game_manager and hasattr(interaction.client, 'game_manager'):
            game_manager = interaction.client.game_manager
        
        # Get config from paginator if available, otherwise use ConfigManager
        config = getattr(self.parent_view, 'config', None) or ConfigManager.get_instance()
        
        # Send the embed without a view for now (GameDetailView was removed during /game-manager redesign)
        # The embed contains all the game details, just without interactive buttons
        try:
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            from core.logging.setup import get_logger
            logger = get_logger("Commands")
            logger.error(f"Error sending game details embed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # Try to send error message
            try:
                await interaction.followup.send(f"`❌` Error loading game details: {str(e)}", ephemeral=True)
            except:
                pass

