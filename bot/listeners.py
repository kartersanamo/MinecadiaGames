import traceback

from assets.functions import log_tasks


async def setup_dm_listeners(client) -> None:
    await _setup_wordle_listener(client)
    await _setup_minesweeper_listener(client)
    await _setup_hangman_listener(client)


async def _setup_wordle_listener(client) -> None:
    try:
        from games.dm.wordle import WordleListener

        if not client.wordle_listener:
            client.wordle_listener = WordleListener(client)
            log_tasks.info("Created WordleListener instance")
            await client.add_cog(client.wordle_listener)
            log_tasks.info("Added WordleListener cog")

        if client.game_manager and hasattr(client.game_manager, "dm_games"):
            wordle_game = client.game_manager.dm_games.get("Wordle")
            if wordle_game:
                client.wordle_listener.set_wordle_game(wordle_game)
                log_tasks.info("Wordle listener: Set wordle_game instance")
            else:
                log_tasks.warning("Wordle listener: wordle_game not found in dm_games")
        else:
            log_tasks.warning("Wordle listener: game_manager or dm_games not available")
    except Exception as e:
        log_tasks.error(f"Failed to load Wordle listener: {e}")
        log_tasks.error(traceback.format_exc())


async def _setup_minesweeper_listener(client) -> None:
    try:
        from games.dm.minesweeper import MinesweeperListener

        if not client.minesweeper_listener:
            client.minesweeper_listener = MinesweeperListener(client)
            log_tasks.info("Created MinesweeperListener instance")
            await client.add_cog(client.minesweeper_listener)
            log_tasks.info("Added MinesweeperListener cog")

        if client.game_manager and hasattr(client.game_manager, "dm_games"):
            client.minesweeper_listener.set_minesweeper_game(
                client.game_manager.dm_games.get("Minesweeper")
            )
    except Exception as e:
        log_tasks.error(f"Failed to load Minesweeper listener: {e}")


async def _setup_hangman_listener(client) -> None:
    try:
        from games.dm.hangman import HangmanListener

        if not client.hangman_listener:
            client.hangman_listener = HangmanListener(client)
            log_tasks.info("Created HangmanListener instance")
            await client.add_cog(client.hangman_listener)
            log_tasks.info("Added HangmanListener cog")

        if client.game_manager and hasattr(client.game_manager, "dm_games"):
            hangman_game = client.game_manager.dm_games.get("Hangman")
            if hangman_game:
                client.hangman_listener.set_hangman_game(hangman_game)
                log_tasks.info("Hangman listener: Set hangman_game instance")
            else:
                log_tasks.warning("Hangman listener: hangman_game not found in dm_games")
        else:
            log_tasks.warning("Hangman listener: game_manager or dm_games not available")
    except Exception as e:
        log_tasks.error(f"Failed to load Hangman listener: {e}")
        log_tasks.error(traceback.format_exc())


async def on_message(client, message) -> None:
    if client.wordle_listener:
        await client.wordle_listener.on_message(message)
    await client.process_commands(message)
