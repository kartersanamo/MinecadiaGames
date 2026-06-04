import discord
from core.config.manager import ConfigManager
from typing import List


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
