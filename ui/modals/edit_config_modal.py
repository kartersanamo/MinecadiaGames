import discord
from core.config.manager import ConfigManager
import json
from typing import List


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
