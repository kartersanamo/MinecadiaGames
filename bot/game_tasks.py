import asyncio

from core.loggers import log_tasks


async def ensure_game_tasks_running(client) -> None:
    if not client.game_manager:
        return

    if client.game_manager.chat_game_running:
        if client.game_manager.chat_game_task is None or client.game_manager.chat_game_task.done():
            log_tasks.warning("Chat game task is not running, restarting...")
            try:
                if client.game_manager.chat_game_task and client.game_manager.chat_game_task.done():
                    try:
                        await client.game_manager.chat_game_task
                    except Exception as e:
                        log_tasks.error(f"Chat game task exception: {e}")
            except Exception:
                pass
            client.game_manager.chat_game_task = asyncio.create_task(
                client.game_manager._chat_game_loop()
            )
            log_tasks.info("Chat game task restarted")

    if client.game_manager.dm_game_running:
        if client.game_manager.dm_game_task is None or client.game_manager.dm_game_task.done():
            log_tasks.warning("DM game task is not running, restarting...")
            try:
                if client.game_manager.dm_game_task and client.game_manager.dm_game_task.done():
                    try:
                        await client.game_manager.dm_game_task
                    except Exception as e:
                        log_tasks.error(f"DM game task exception: {e}")
            except Exception:
                pass
            client.game_manager.dm_game_task = asyncio.create_task(
                client.game_manager._dm_game_loop()
            )
            log_tasks.info("DM game task restarted")
