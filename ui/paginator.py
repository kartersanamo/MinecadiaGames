import discord
import re
from collections.abc import Awaitable, Callable
from typing import List, Optional
from core.config.manager import ConfigManager


from services.asset_path_service import AssetPathService
from services.embed_service import EmbedService
from ui.views.game_detail_view import GameDetailView, build_game_detail_payload

LOGO = AssetPathService.LOGO_PATH


class Paginator(discord.ui.View):
    def __init__(self, timeout: Optional[float] = None, bot=None):
        # Use None for persistent views (default)
        super().__init__(timeout=None)
        self.bot = bot
        self.config = ConfigManager.get_instance()
        self.data: List[str] = []
        self.title: str = ""
        self.sep: int = 5
        self.current_page: int = 1
        self.category: Optional[discord.CategoryChannel] = None
        self.count: bool = False
        self.games: Optional[List[str]] = None
        self.ephemeral: bool = False
        self.back_callback: Optional[Callable[[discord.Interaction], Awaitable[None]]] = None
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
            except Exception:
                # Fallback to followup if response fails
                msg = await interaction.followup.send(embed=embed, view=self, ephemeral=True)
            return msg
        elif self.games:
            # For games with non-ephemeral, edit the original message
            message = interaction.message
            if message is not None:
                await message.edit(view=self, content="")
            await self.update_message(interaction)
        else:
            # Regular non-ephemeral response
            try:
                await interaction.response.send_message(view=self, content="")
            except Exception:
                await interaction.edit_original_response(view=self, content="")
            await self.update_message(interaction)

    def _resolve_logo_url(self) -> Optional[str]:
        config = ConfigManager.get_instance()
        logo_path = config.get('config', 'LOGO') or LOGO
        if self.bot and getattr(self.bot, 'app', None):
            return self.bot.app.embeds.get_logo_url(logo_path)
        return EmbedService.get_logo_url(logo_path)
    
    def create_embed(self) -> discord.Embed:
        config = ConfigManager.get_instance()
        embed = discord.Embed(title=self.title, description="", color=discord.Color.from_str(config.get('config', 'EMBED_COLOR')))
        footer_text = self.get_footer_text()
        description = ""
        
        if self.data and self.data[0] == "No data found.":
            description = "No data found."
        else:
            if self.count:
                for index, item in enumerate(self.get_current_page_data()):
                    description += f"**{(self.sep*self.current_page)-(self.sep-(index+1))}.** {item}\n"
            else:
                for item in self.get_current_page_data():
                    description += f"{item}\n"
        embed.description = description
        
        if footer_text:
            logo_url = self._resolve_logo_url()
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
            message = interaction.message
            if message is not None:
                await message.edit(embeds=[embed], view=self)
            else:
                await interaction.edit_original_response(embed=embed, view=self)
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
        back_handler = self.back_callback
        if callable(back_handler):
            back_button = discord.ui.Button(
                label="← Back",
                style=discord.ButtonStyle.grey,
                custom_id="back_button",
                row=2
            )
            async def back_callback(interaction: discord.Interaction):
                await interaction.response.defer(ephemeral=self.ephemeral)
                await back_handler(interaction)

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
        game_id = int(self.values[0])
        await interaction.response.defer(ephemeral=True)
        payload = await build_game_detail_payload(self.parent_view.bot, self.parent_view.config, game_id)
        if not payload:
            await interaction.followup.send(f"Game #{game_id} not found.", ephemeral=True)
            return

        view = GameDetailView(
            self.parent_view.bot,
            self.parent_view.config,
            payload["game_id"],
            payload["game_name"],
            payload["is_dm_game"],
            payload["game_data"],
        )

        await interaction.followup.send(embed=payload["embed"], view=view, ephemeral=True)

