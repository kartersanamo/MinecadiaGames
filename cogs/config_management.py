from discord.ext import commands
from discord import app_commands
import discord
from core.config.manager import ConfigManager
from core.logging.setup import get_logger
from pathlib import Path
import json
from typing import Any, Dict, List


class ConfigManagement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = ConfigManager.get_instance()
        self.logger = get_logger("Commands")
    
    def _check_admin(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            return False
        
        admin_roles = self.config.get('config', 'ADMIN_ROLES', [])
        user_roles = [role.name for role in interaction.user.roles]
        
        if "*" in admin_roles:
            return True
        
        return any(role in admin_roles for role in user_roles)
    
    def _get_available_configs(self) -> List[str]:
        """Get list of available config files."""
        config_dir = Path(__file__).parent.parent / "assets" / "Configs"
        configs = []
        
        # Main config files
        for file in config_dir.glob("*.json"):
            if file.stem not in ['winners_history']:  # Exclude data files
                configs.append(file.stem)
        
        # Game configs
        games_dir = config_dir / "games"
        if games_dir.exists():
            for file in games_dir.glob("*.json"):
                configs.append(f"games/{file.stem}")
        
        return sorted(configs)
    
    def _format_config_value(self, value: Any, max_depth: int = 3, current_depth: int = 0) -> str:
        """Format a config value for display."""
        if current_depth >= max_depth:
            return str(value)[:100] + "..." if len(str(value)) > 100 else str(value)
        
        if isinstance(value, dict):
            if not value:
                return "{}"
            items = []
            for k, v in list(value.items())[:10]:  # Limit to 10 items
                formatted_v = self._format_config_value(v, max_depth, current_depth + 1)
                items.append(f"  {k}: {formatted_v}")
            if len(value) > 10:
                items.append(f"  ... ({len(value) - 10} more items)")
            return "{\n" + "\n".join(items) + "\n}"
        elif isinstance(value, list):
            if not value:
                return "[]"
            items = []
            for i, v in enumerate(value[:10]):  # Limit to 10 items
                formatted_v = self._format_config_value(v, max_depth, current_depth + 1)
                items.append(f"  [{i}]: {formatted_v}")
            if len(value) > 10:
                items.append(f"  ... ({len(value) - 10} more items)")
            return "[\n" + "\n".join(items) + "\n]"
        else:
            return json.dumps(value) if not isinstance(value, str) else value
    
    @app_commands.command(name="config-get", description="Get a configuration value")
    @app_commands.describe(config_file="Configuration file name", key="Configuration key (use dots for nested)")
    async def config_get(
        self,
        interaction: discord.Interaction,
        config_file: str,
        key: str
    ):
        if not self._check_admin(interaction):
            await interaction.response.send_message("`❌` You don't have permission to use this command.", ephemeral=True)
            return
        
        try:
            value = self.config.get(config_file, key)
            if value is None:
                await interaction.response.send_message(
                    f"`❌` Key `{key}` not found in `{config_file}`",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"`{config_file}.{key}` = `{json.dumps(value)}`",
                    ephemeral=True
                )
        except Exception as e:
            await interaction.response.send_message(
                f"`❌` Error: {str(e)}",
                ephemeral=True
            )
    
    @app_commands.command(name="config-set", description="Set a configuration value")
    @app_commands.describe(
        config_file="Configuration file name",
        key="Configuration key (use dots for nested)",
        value="New value (JSON format)"
    )
    async def config_set(
        self,
        interaction: discord.Interaction,
        config_file: str,
        key: str,
        value: str
    ):
        if not self._check_admin(interaction):
            await interaction.response.send_message("`❌` You don't have permission to use this command.", ephemeral=True)
            return
        
        try:
            parsed_value = json.loads(value)
            success = self.config.set(config_file, key, parsed_value)
            
            if success:
                self.config.reload(config_file)
                await interaction.response.send_message(
                    f"`✅` Successfully set `{config_file}.{key}` = `{value}`",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"`❌` Failed to set configuration value.",
                    ephemeral=True
                )
        except json.JSONDecodeError:
            await interaction.response.send_message(
                "`❌` Invalid JSON format. Please provide valid JSON.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"`❌` Error: {str(e)}",
                ephemeral=True
            )
    
    @app_commands.command(name="config-reload", description="Reload a configuration file")
    @app_commands.describe(config_file="Configuration file name to reload")
    async def config_reload(self, interaction: discord.Interaction, config_file: str):
        if not self._check_admin(interaction):
            await interaction.response.send_message("`❌` You don't have permission to use this command.", ephemeral=True)
            return
        
        try:
            self.config.reload(config_file)
            await interaction.response.send_message(
                f"`✅` Successfully reloaded `{config_file}`",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"`❌` Error: {str(e)}",
                ephemeral=True
            )
    
    @app_commands.command(name="config-manager", description="Interactive configuration manager")
    async def config_manager(self, interaction: discord.Interaction):
        if not self._check_admin(interaction):
            await interaction.response.send_message("`❌` You don't have permission to use this command.", ephemeral=True)
            return
        
        configs = self._get_available_configs()
        if not configs:
            await interaction.response.send_message("`❌` No configuration files found.", ephemeral=True)
            return
        
        view = ConfigManagerView(self.config, configs)
        embed = discord.Embed(
            title="Configuration Manager",
            description="Select a configuration file to view and edit:",
            color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR'))
        )
        from utils.helpers import get_embed_logo_url
        logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
        embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
        await interaction.response.send_message(embed=embed, view=view)


class ConfigManagerView(discord.ui.View):
    def __init__(self, config_manager: ConfigManager, available_configs: List[str]):
        super().__init__(timeout=None)
        self.config_manager = config_manager
        self.available_configs = available_configs
        self.current_config = None
        self.current_path = []
        
        # Add select menu for config files
        self.config_select = discord.ui.Select(
            placeholder="Select a configuration file...",
            options=[
                discord.SelectOption(label=config, value=config, description=f"View {config} configuration")
                for config in available_configs[:25]  # Discord limit
            ],
            custom_id="config_manager_select",
            row=0
        )
        self.config_select.callback = self.config_selected
        self.add_item(self.config_select)
    
    async def config_selected(self, interaction: discord.Interaction):
        config_name = self.config_select.values[0]
        self.current_config = config_name
        self.current_path = []
        
        try:
            config_data = self.config_manager.get(config_name)
            view = ConfigViewer(self.config_manager, config_name, config_data, [])
            embed = await view.create_embed()
            await interaction.response.edit_message(embed=embed, view=view)
        except Exception as e:
            await interaction.response.send_message(
                f"`❌` Error loading config: {str(e)}",
                ephemeral=True
            )


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
            from utils.helpers import get_embed_logo_url
            logo_url = get_embed_logo_url(self.config_manager.get('config', 'LOGO'))
            embed.set_footer(text=self.config_manager.get('config', 'FOOTER'), icon_url=logo_url)
            await interaction.response.edit_message(embed=embed, view=view)
        except Exception as e:
            await interaction.response.send_message(f"`❌` Error reloading: {str(e)}", ephemeral=True)
    


class EditConfigModal(discord.ui.Modal, title="Edit Configuration Value"):
    def __init__(self, config_manager: ConfigManager, config_name: str, path: List[str], current_value: str):
        super().__init__()
        self.config_manager = config_manager
        self.config_name = config_name
        self.path = path
        self.value_input = discord.ui.TextInput(
            label="New Value (JSON format)",
            placeholder='Enter value (e.g., "string", 123, true, ["array"], {"key": "value"})',
            default=current_value[:4000] if len(current_value) <= 4000 else current_value[:3997] + "...",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=4000
        )
        self.add_item(self.value_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Parse the JSON value
            new_value = json.loads(self.value_input.value)
            
            # Set the value
            key_path = ".".join(self.path) if self.path else None
            success = self.config_manager.set(self.config_name, key_path, new_value) if key_path else False
            
            if not success and key_path:
                # Try setting directly if path-based set fails
                config_data = self.config_manager.get(self.config_name)
                # Navigate to parent and set
                parent = config_data
                for key in self.path[:-1]:
                    parent = parent[key]
                parent[self.path[-1]] = new_value
                # Save the config
                self.config_manager._save_config(self.config_name, config_data)
                success = True
            
            if success:
                self.config_manager.reload(self.config_name)
                # Update the config data in cache
                config_data = self.config_manager.get(self.config_name)
                for key in self.path:
                    config_data = config_data[key]
                
                await interaction.response.send_message(
                    f"`✅` Successfully updated `{self.config_name}`" + (f".{key_path}" if key_path else ""),
                    ephemeral=True
                )
            else:
                # Try direct manipulation
                try:
                    config_data = self.config_manager.get(self.config_name)
                    
                    if not self.path:
                        # Root level - replace entire config
                        config_data = new_value
                    else:
                        # Navigate to parent
                        parent = config_data
                        for key in self.path[:-1]:
                            parent = parent[key]
                        # Set the value
                        parent[self.path[-1]] = new_value
                    
                    # Get the raw config (not merged)
                    mapped_name = self.config_name
                    if mapped_name == 'config':
                        # For 'config', we need to handle bot.json and discord.json separately
                        # For simplicity, save to bot.json
                        mapped_name = 'bot'
                    
                    # Update cache with the modified data
                    if mapped_name not in self.config_manager._cache:
                        self.config_manager._cache[mapped_name] = self.config_manager._load_config(mapped_name)
                    
                    # Update the cached config
                    if not self.path:
                        self.config_manager._cache[mapped_name] = new_value
                    else:
                        parent = self.config_manager._cache[mapped_name]
                        for key in self.path[:-1]:
                            parent = parent[key]
                        parent[self.path[-1]] = new_value
                    
                    # Save to file
                    self.config_manager._save_config(mapped_name, self.config_manager._cache[mapped_name])
                    self.config_manager.reload(self.config_name)
                    await interaction.response.send_message(
                        f"`✅` Successfully updated `{self.config_name}`" + (f".{key_path}" if key_path else ""),
                        ephemeral=True
                    )
                except Exception as e:
                    await interaction.response.send_message(
                        f"`❌` Failed to update configuration: {str(e)}",
                        ephemeral=True
                    )
        except json.JSONDecodeError:
            await interaction.response.send_message(
                "`❌` Invalid JSON format. Please provide valid JSON.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"`❌` Error: {str(e)}",
                ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(ConfigManagement(bot))

