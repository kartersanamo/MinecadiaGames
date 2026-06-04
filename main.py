import asyncio
import os
from pathlib import Path

os.chdir(Path(__file__).resolve().parent)

from core.decorators import task
from core.loggers import log_tasks
from bot import game_tasks, listeners, restore, startup, views
from core.cache.manager import CacheManager
from core.config.manager import ConfigManager
from core.logging.setup import setup_logging
from managers.game_manager import GameManager

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from typing import Optional

_bots_env = (
    Path(__file__).resolve().parent.parent.parent.parent / "Websites" / "Bots" / ".env"
)
if _bots_env.exists():
    load_dotenv(_bots_env)
load_dotenv()

COG_FILES = [
    file.split(".")[0].title()
    for file in os.listdir("cogs/")
    if file.endswith(".py") and not file.startswith("_")
]


class Client(commands.Bot):
    def __init__(self):
        setup_logging()
        self.config = ConfigManager.get_instance()
        super().__init__(command_prefix=".", intents=discord.Intents.all())
        self.game_manager: Optional[GameManager] = None
        self.wordle_listener = None
        self.minesweeper_listener = None
        self.hangman_listener = None

    @task("Initialize Database Pool")
    async def initialize_database_pool(self):
        log_tasks.info("Initializing database pool in background...")
        asyncio.create_task(startup.initialize_database_pool_background(self))

    @task("Start Cache Cleanup")
    async def start_cache_cleanup(self):
        cache = CacheManager.get_instance()
        await cache.start_cleanup_task()
        log_tasks.info("Cache cleanup task started")

    @task("Setup Cogs")
    async def setup_cogs(self):
        await startup.load_extensions(self)

    @task("Register Analytics")
    async def register_analytics(self):
        await startup.register_analytics(self)

    @task("Start Dashboard HTTP")
    async def setup_dashboard_http(self):
        from assets.http.dashboard_http import start_dashboard_http

        await start_dashboard_http(self)

    @task("Setup Hook")
    async def setup_hook(self):
        try:
            log_tasks.info("Starting bot setup...")
            await self.initialize_database_pool()
            await self.start_cache_cleanup()
            await self.setup_cogs()
            await self.register_analytics()
            log_tasks.info("Bot setup complete")
        except Exception as e:
            log_tasks.error(f"Error in setup_hook: {e}", exc_info=True)

    @task("Setup Game Manager")
    async def setup_game_manager(self):
        if not self.game_manager:
            self.game_manager = GameManager(self)
            await self.game_manager.initialize()
        else:
            await game_tasks.ensure_game_tasks_running(self)

    @task("Setup DM Listeners")
    async def setup_dm_listeners(self):
        await listeners.setup_dm_listeners(self)

    @task("Register Persistent Views")
    async def register_persistent_views(self):
        await views.register_persistent_views(self)

    @task("Restore Active Chat Games")
    async def restore_active_chat_games(self):
        await restore.restore_active_chat_games(self)

    @task("Restore Active DM Games")
    async def restore_active_dm_games(self):
        await restore.restore_active_dm_games(self)

    @task("Update Presence")
    async def update_presence(self):
        presence = self.config.get("config", "PRESENCE", "play.minecadia.com")
        await client.change_presence(activity=discord.Game(name=presence))
        log_tasks.info(f"Updated the bot's presence to {presence}")

    @task("Remove Help")
    async def remove_help(self):
        try:
            client.remove_command("help")
        except Exception:
            pass

    @task("Sync Command Tree")
    async def sync_command_tree(self):
        try:
            synced = await self.tree.sync()
            log_tasks.info(f"Synced {len(synced)} commands")
        except Exception as e:
            log_tasks.error(f"Failed to sync commands: {e}")

    @task("Logging in")
    async def on_ready(self):
        await self.setup_game_manager()
        await self.setup_dm_listeners()

        try:
            await self.register_persistent_views()
            log_tasks.info("Registered persistent views")
        except Exception as e:
            log_tasks.error(f"Failed to register persistent views: {e}")

        try:
            await self.restore_active_chat_games()
            log_tasks.info("Restored active chat games")
        except Exception as e:
            log_tasks.error(f"Failed to restore active chat games: {e}")

        try:
            await self.restore_active_dm_games()
            log_tasks.info("Restored active DM games")
        except Exception as e:
            log_tasks.error(f"Failed to restore active DM games: {e}")

        await self.update_presence()
        await self.remove_help()
        await self.sync_command_tree()

        try:
            await self.setup_dashboard_http()
        except Exception as e:
            log_tasks.error(f"Failed to start dashboard HTTP: {e}")

        log_tasks.info(f"Logged in as {client.user} ({client.user.id})")

    async def on_resume(self):
        log_tasks.info("Bot connection resumed - checking game tasks")
        if self.game_manager:
            await game_tasks.ensure_game_tasks_running(self)

    async def on_message(self, message: discord.Message):
        await listeners.on_message(self, message)

    async def close(self):
        await startup.shutdown(self)
        await super().close()


client = Client()


@task("Games Reload Command", True)
async def games_reload_command(interaction: discord.Interaction, cog: str):
    if interaction.guild is None:
        return await interaction.response.send_message(
            content="Commands cannot be ran in DMs!", ephemeral=True
        )
    if cog not in COG_FILES:
        await interaction.response.send_message(
            f"Invalid cog name **{cog}.py**", ephemeral=True
        )
        return
    await client.reload_extension(f"cogs.{cog.lower()}")
    await interaction.response.send_message(
        f"Successfully reloaded **{cog}.py**", ephemeral=True
    )


async def cog_autocomplete(_: discord.Interaction, current: str):
    return [
        app_commands.Choice(name=cog, value=cog)
        for cog in COG_FILES
        if current.lower() in cog.lower()
    ]


@client.tree.command(name="games-reload", description="Reloads a Cog Class")
@app_commands.autocomplete(cog=cog_autocomplete)
async def gamesreload(interaction: discord.Interaction, cog: str):
    await games_reload_command(interaction, cog)


@gamesreload.error
async def gamesreload_error(
    interaction: discord.Interaction, error: discord.app_commands.AppCommandError
):
    if interaction.response.is_done():
        await interaction.followup.send(content=error, ephemeral=True)
    else:
        await interaction.response.send_message(content=error, ephemeral=True)


TOKEN = os.getenv("DISCORD_TOKEN") or client.config.get("config", "TOKEN")
if not TOKEN:
    raise ValueError("Set DISCORD_TOKEN in .env or 'token' in assets/Configs/bot.json")

if __name__ == "__main__":
    client.run(TOKEN)
