from services.embed_service import EmbedService
from discord.ext import commands
from discord import app_commands
import discord
from core.config.manager import ConfigManager
from core.logging.setup import get_logger
from pathlib import Path
import json
from typing import Any, Dict, List


class ConfigViewer(discord.ui.View):
    def __init__(self, config_manager: ConfigManager, config_name: str, config_data: Any, path: List[str]):
        super().__init__(timeout=None)
        self.config_manager = config_manager
        self.config_name = config_name
        self.config_data = config_data
        self.path = path
        
        # Add navigation buttons
        if path:
            back_btn = discord.ui.Button(label="← Back", style=discord.ButtonStyle.grey, custom_id="config_viewer_back", row=0)
            back_btn.callback = self.go_back
            self.add_item(back_btn)
        
        # Add select menu for navigating into dicts/lists
        if isinstance(config_data, dict) and len(config_data) > 0:
            select = discord.ui.Select(
                placeholder="Navigate into a key...",
                options=[
                    discord.SelectOption(
                        label=key[:100],
                        value=key,
                        description=self._preview_value(value)[:100]
                    )
                    for key, value in list(config_data.items())[:25]  # Discord limit
                ],
                custom_id="config_viewer_dict_select",
                row=1
            )
            select.callback = self.navigate_into
            self.add_item(select)
        elif isinstance(config_data, list) and len(config_data) > 0:
            select = discord.ui.Select(
                placeholder="Navigate into an item...",
                options=[
                    discord.SelectOption(
                        label=f"Item {i}",
                        value=str(i),
                        description=self._preview_value(item)[:100]
                    )
                    for i, item in enumerate(config_data[:25])  # Discord limit
                ],
                custom_id="config_viewer_list_select",
                row=1
            )
            select.callback = self.navigate_into
            self.add_item(select)
        
        # Add edit button for current value if it's a leaf node
        if not isinstance(config_data, (dict, list)) or (isinstance(config_data, dict) and len(config_data) == 0) or (isinstance(config_data, list) and len(config_data) == 0):
            edit_btn = discord.ui.Button(label="✏️ Edit Value", style=discord.ButtonStyle.primary, custom_id="config_viewer_edit", row=2)
            edit_btn.callback = self.edit_value
            self.add_item(edit_btn)
        
        # Add reload button
        reload_btn = discord.ui.Button(label="🔄 Reload", style=discord.ButtonStyle.secondary, custom_id="config_viewer_reload", row=2)
        reload_btn.callback = self.reload_config
        self.add_item(reload_btn)
    
    async def navigate_into(self, interaction: discord.Interaction):
        """Navigate into a selected key/item."""
        selected = interaction.data.get('values', [])
        if not selected:
            return
        
        key = selected[0]
        
        if isinstance(self.config_data, dict) and key in self.config_data:
            new_path = self.path + [key]
            new_data = self.config_data[key]
            view = ConfigViewer(self.config_manager, self.config_name, new_data, new_path)
            embed = await view.create_embed()
            await interaction.response.edit_message(embed=embed, view=view)
        elif isinstance(self.config_data, list):
            try:
                index = int(key)
                if 0 <= index < len(self.config_data):
                    new_path = self.path + [str(index)]
                    new_data = self.config_data[index]
                    view = ConfigViewer(self.config_manager, self.config_name, new_data, new_path)
                    embed = await view.create_embed()
                    await interaction.response.edit_message(embed=embed, view=view)
            except (ValueError, IndexError):
                await interaction.response.send_message("Invalid selection.", ephemeral=True)
    
    async def create_embed(self) -> discord.Embed:
        """Create embed showing the current config view."""
        embed = discord.Embed(
            title=f"Config: {self.config_name}",
            color=discord.Color.from_str(self.config_manager.get('config', 'EMBED_COLOR'))
        )
        
        path_str = " → ".join(self.path) if self.path else "Root"
        embed.description = f"**Path:** `{path_str}`\n\n"
        
        if isinstance(self.config_data, dict):
            if not self.config_data:
                embed.description += "Empty object `{}`"
            else:
                embed.description += "**Keys:**\n"
                for key in list(self.config_data.keys())[:20]:  # Limit to 20 keys
                    value = self.config_data[key]
                    value_preview = self._preview_value(value)
                    embed.description += f"• `{key}`: {value_preview}\n"
                if len(self.config_data) > 20:
                    embed.description += f"\n... and {len(self.config_data) - 20} more keys"
        elif isinstance(self.config_data, list):
            if not self.config_data:
                embed.description += "Empty array `[]`"
            else:
                embed.description += f"**Array with {len(self.config_data)} items:**\n"
                for i, item in enumerate(self.config_data[:10]):  # Limit to 10 items
                    value_preview = self._preview_value(item)
                    embed.description += f"• `[{i}]`: {value_preview}\n"
                if len(self.config_data) > 10:
                    embed.description += f"\n... and {len(self.config_data) - 10} more items"
        else:
            embed.add_field(name="Current Value", value=f"```json\n{json.dumps(self.config_data, indent=2)}\n```", inline=False)
        
        return embed
    
    def _preview_value(self, value: Any) -> str:
        """Get a preview of a value."""
        if isinstance(value, dict):
            return f"`{{ {len(value)} keys }}`"
        elif isinstance(value, list):
            return f"`[ {len(value)} items ]`"
        elif isinstance(value, str):
            return f"`\"{value[:30]}{'...' if len(value) > 30 else ''}\"`"
        else:
            return f"`{value}`"
    
    async def go_back(self, interaction: discord.Interaction):
        """Navigate back in the config structure."""
        if not self.path:
            await interaction.response.send_message("Already at root level.", ephemeral=True)
            return
        
        # Navigate back
        new_path = self.path[:-1]
        if new_path:
            # Navigate to parent
            parent_data = self.config_manager.get(self.config_name)
            for key in new_path:
                parent_data = parent_data[key]
        else:
            parent_data = self.config_manager.get(self.config_name)
        
        view = ConfigViewer(self.config_manager, self.config_name, parent_data, new_path)
        embed = await view.create_embed()
        await interaction.response.edit_message(embed=embed, view=view)
    
    async def edit_value(self, interaction: discord.Interaction):
        """Open modal to edit the current value."""
        current_value = json.dumps(self.config_data, indent=2) if not isinstance(self.config_data, str) else self.config_data
        path_str = " → ".join(self.path) if self.path else "root"
        
        modal = EditConfigModal(self.config_manager, self.config_name, self.path, current_value)
        await interaction.response.send_modal(modal)
    
    async def reload_config(self, interaction: discord.Interaction):
        """Reload the config file."""
        try:
            self.config_manager.reload(self.config_name)
            # Reload the data
            config_data = self.config_manager.get(self.config_name)
            for key in self.path:
                config_data = config_data[key]
            
            view = ConfigViewer(self.config_manager, self.config_name, config_data, self.path)
            embed = await view.create_embed()
                        logo_url = self.bot.app.embeds.get_logo_url(self.config_manager.get('config', 'LOGO'))
            embed.set_footer(text=self.config_manager.get('config', 'FOOTER'), icon_url=logo_url)
            await interaction.response.edit_message(embed=embed, view=view)
        except Exception as e:
            await interaction.response.send_message(f"`❌` Error reloading: {str(e)}", ephemeral=True)
