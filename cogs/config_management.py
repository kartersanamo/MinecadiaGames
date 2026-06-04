from discord.ext import commands
from discord import app_commands
import discord
from core.config.manager import ConfigManager
from core.logging.setup import get_logger
from pathlib import Path
import json
from typing import Any, List
from ui.views.config_manager_view import ConfigManagerView

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
        config_dir = Path(__file__).parent.parent / "assets" / "configs"
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
        logo_url = self.bot.app.embeds.get_logo_url(self.config.get('config', 'LOGO'))
        embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
        await interaction.response.send_message(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(ConfigManagement(bot))
