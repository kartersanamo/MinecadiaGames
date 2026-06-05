import asyncio
from pathlib import Path

from core.loggers import log_tasks
from core.cache.manager import CacheManager
from core.database.pool import DatabasePool


async def initialize_database_pool_background(client) -> None:
    try:
        db_pool = await DatabasePool.get_instance()
        try:
            await asyncio.wait_for(db_pool.initialize(), timeout=15.0)
            log_tasks.info("Database pool initialized in background")
        except asyncio.TimeoutError:
            log_tasks.warning(
                "Database pool initialization timed out after 15 seconds - will retry on first use"
            )
        except Exception as init_e:
            log_tasks.warning(
                f"Database pool initialization failed: {init_e} - will retry on first use"
            )
    except Exception as e:
        log_tasks.error(
            f"Failed to get database pool instance: {e} - database features may not work",
            exc_info=True,
        )


async def load_extensions(client) -> None:
    cog_dir = Path(__file__).resolve().parent.parent / "cogs"
    if not cog_dir.exists():
        return
    for filename in cog_dir.iterdir():
        if filename.suffix == ".py" and not filename.name.startswith("_"):
            ext_name = f"cogs.{filename.stem}"
            try:
                await client.load_extension(ext_name)
                log_tasks.info(f"Loaded extension: {ext_name}")
            except Exception as e:
                log_tasks.error(f"Failed to load {ext_name}: {e}")


async def register_analytics(client) -> None:
    from core.analytics.register import register_command_tracking

    await register_command_tracking(client)


async def shutdown(client) -> None:
    try:
        log_tasks.info("Bot shutting down - closing database pool")
        db = await DatabasePool.get_instance()
        if db is not None:
            try:
                await db.close()
                log_tasks.info("Database pool closed")
            except Exception as e:
                log_tasks.error(f"Error closing database pool: {e}")
    except Exception as e:
        log_tasks.error(f"Error during database pool shutdown: {e}")

    try:
        log_tasks.info("Cancelling cache cleanup task")
        cache = CacheManager.get_instance()
        cleanup_task = getattr(cache, "_cleanup_task", None)
        if cleanup_task and not cleanup_task.done():
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass
        log_tasks.info("Cache cleanup task cancelled")
    except Exception as e:
        log_tasks.error(f"Error cancelling cache cleanup task: {e}")
