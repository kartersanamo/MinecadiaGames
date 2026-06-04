import asyncio
import json
import re
import traceback
from datetime import datetime, timezone
from typing import Optional, Tuple

from core.loggers import log_tasks
from core.database.pool import DatabasePool


async def restore_active_chat_games(client) -> None:
    try:
        db = await DatabasePool.get_instance()
        current_time = int(datetime.now(timezone.utc).timestamp())
        chat_config = client.config.get("chat_games")
        game_length = chat_config.get("GAME_LENGTH") or chat_config.get("game_duration", 600)

        try:
            active_games = await db.execute(
                """
                SELECT game_id, game_name, refreshed_at, end_time
                FROM games
                WHERE dm_game = FALSE
                AND (status = 'Started' OR status IS NULL)
                AND (end_time > %s OR (end_time IS NULL AND refreshed_at + %s > %s))
                ORDER BY refreshed_at DESC
                """,
                (current_time, game_length, current_time),
            )
        except Exception:
            try:
                active_games = await db.execute(
                    """
                    SELECT game_id, game_name, refreshed_at
                    FROM games
                    WHERE dm_game = FALSE
                    AND refreshed_at + %s > %s
                    ORDER BY refreshed_at DESC
                    """,
                    (game_length, current_time),
                )
            except Exception:
                active_games = await db.execute(
                    """
                    SELECT game_id, game_name, refreshed_at
                    FROM games
                    WHERE dm_game = FALSE
                    AND refreshed_at > %s
                    ORDER BY refreshed_at DESC
                    LIMIT 10
                    """,
                    (current_time - 3600,),
                )

        if not active_games:
            log_tasks.info("No active chat games to restore")
            return

        log_tasks.info(f"Found {len(active_games)} active chat games to restore")

        for game in active_games:
            try:
                game_id = game["game_id"]
                game_name = game["game_name"]
                refreshed_at = int(game.get("refreshed_at", 0))
                end_time = game.get("end_time")

                if not end_time:
                    end_time = refreshed_at + game_length

                if end_time <= current_time:
                    try:
                        await db.execute(
                            "UPDATE games SET status = 'Finished' WHERE game_id = %s",
                            (game_id,),
                        )
                    except Exception:
                        pass
                    continue

                remaining_time = end_time - current_time
                asyncio.create_task(
                    restore_chat_game_timer(client, game_id, game_name, end_time, remaining_time)
                )
            except Exception as e:
                log_tasks.error(f"Error restoring game {game.get('game_id')}: {e}")
                log_tasks.error(traceback.format_exc())

    except Exception as e:
        log_tasks.error(f"Error restoring active chat games: {e}")
        log_tasks.error(traceback.format_exc())


def parse_dm_game_from_embed_title(title: str) -> Optional[Tuple[str, int]]:
    if not title or "#" not in title:
        return None
    match = re.search(r"#(\d+)", title)
    if not match:
        return None
    game_id = int(match.group(1))
    prefix = title.split("#")[0].strip()
    prefix = re.sub(r"\s*🧪\s*TEST\s*GAME\s*🧪\s*$", "", prefix, flags=re.IGNORECASE).strip()
    title_to_type = {
        "2048": "2048",
        "TicTacToe": "tictactoe",
        "Connect Four": "connectfour",
        "Memory": "memory",
        "Minesweeper": "minesweeper",
        "Hangman": "hangman",
    }
    game_type = title_to_type.get(prefix)
    if game_type is None:
        return None
    return (game_type, game_id)


async def get_most_recent_dm_game_for_user(client, user_id: int) -> Optional[Tuple[str, int]]:
    try:
        user = await client.fetch_user(user_id)
        if not user:
            return None
        channel = user.dm_channel or await user.create_dm()
        async for message in channel.history(limit=50):
            if message.author.id != client.user.id:
                continue
            if not message.embeds:
                continue
            parsed = parse_dm_game_from_embed_title(message.embeds[0].title)
            if parsed:
                return parsed
        return None
    except Exception as e:
        log_tasks.debug(f"Could not get most recent DM game for user {user_id}: {e}")
        return None


async def end_dm_game_in_db(game_type: str, game_id: int, user_id: int) -> None:
    try:
        db = await DatabasePool.get_instance()
        now = int(datetime.now(timezone.utc).timestamp())
        table_map = {
            "2048": ("users_2048", "status = 'Lost'"),
            "tictactoe": ("users_tictactoe", "won = 'Lost'"),
            "connectfour": ("users_connectfour", "status = 'Lost'"),
            "memory": ("users_memory", "won = 'Lost'"),
            "minesweeper": ("users_minesweeper", "won = 'Lost'"),
            "hangman": ("users_hangman", "won = 'Lost'"),
        }
        table, set_clause = table_map.get(game_type, (None, None))
        if not table:
            return
        await db.execute(
            f"UPDATE {table} SET {set_clause}, ended_at = %s WHERE user_id = %s AND game_id = %s",
            (now, user_id, game_id),
        )
        log_tasks.debug(f"Ended non-most-recent DM game {game_type} #{game_id} for user {user_id}")
    except Exception as e:
        log_tasks.warning(f"Error ending DM game {game_type} #{game_id} for user {user_id}: {e}")


async def restore_active_dm_games(client) -> None:
    try:
        db = await DatabasePool.get_instance()
        game_tables = {
            "users_2048": "2048",
            "users_tictactoe": "tictactoe",
            "users_connectfour": "connectfour",
            "users_memory": "memory",
            "users_minesweeper": "minesweeper",
            "users_hangman": "hangman",
        }

        restored_count = 0
        ended_count = 0

        for table_name, game_type in game_tables.items():
            try:
                if table_name in ["users_2048", "users_connectfour"]:
                    status_condition = "status = 'Started'"
                else:
                    status_condition = "won = 'Started'"

                active_games = await db.execute(
                    f"""
                    SELECT game_id, user_id, game_state
                    FROM {table_name}
                    WHERE {status_condition}
                    AND (ended_at = 0 OR ended_at IS NULL)
                    AND game_state IS NOT NULL
                    ORDER BY started_at DESC
                    LIMIT 100
                    """
                )

                if not active_games:
                    continue

                game_type_restored = 0
                game_type_ended = 0

                for game in active_games:
                    try:
                        game_id = game["game_id"]
                        user_id = game["user_id"]
                        game_state_json = game.get("game_state")

                        if not game_state_json:
                            continue

                        most_recent = await get_most_recent_dm_game_for_user(client, user_id)
                        if most_recent is None or most_recent != (game_type, game_id):
                            log_tasks.debug(
                                f"Ending non-most-recent {game_type} game #{game_id} for user {user_id} (most recent: {most_recent})"
                            )
                            await end_dm_game_in_db(game_type, game_id, user_id)
                            game_type_ended += 1
                            ended_count += 1
                            continue

                        try:
                            if isinstance(game_state_json, str):
                                game_state = json.loads(game_state_json)
                            else:
                                game_state = game_state_json
                        except Exception as e:
                            log_tasks.error(
                                f"Error parsing game_state for {game_type} game {game_id}: {e}"
                            )
                            continue

                        if game_type == "wordle":
                            continue

                        restored_views = await restore_dm_game_view(
                            client, game_type, game_id, user_id, game_state
                        )

                        if restored_views:
                            if isinstance(restored_views, list):
                                for view in restored_views:
                                    client.add_view(view)
                                    game_type_restored += 1
                                    restored_count += 1
                            else:
                                client.add_view(restored_views)
                                game_type_restored += 1
                                restored_count += 1
                            log_tasks.debug(
                                f"Restored {game_type} game #{game_id} for user {user_id}"
                            )

                    except Exception as e:
                        log_tasks.error(
                            f"Error restoring {game_type} game {game.get('game_id')}: {e}"
                        )
                        log_tasks.error(traceback.format_exc())

                if game_type_restored > 0 or game_type_ended > 0:
                    log_tasks.info(
                        f"{game_type}: Restored {game_type_restored} most recent game(s), ended {game_type_ended} old game(s)"
                    )

            except Exception as e:
                log_tasks.error(f"Error querying {table_name} for active games: {e}")
                log_tasks.error(traceback.format_exc())

        if restored_count > 0 or ended_count > 0:
            log_tasks.info(
                f"DM Games Summary: Restored {restored_count} most recent game(s), ended {ended_count} old game(s)"
            )
        else:
            log_tasks.info("No active DM games to restore")

    except Exception as e:
        log_tasks.error(f"Error restoring active DM games: {e}")
        log_tasks.error(traceback.format_exc())


async def restore_dm_game_view(client, game_type: str, game_id: int, user_id: int, game_state: dict):
    try:
        config = client.config

        if game_type == "2048":
            from games.dm.twenty_forty_eight import TwentyFortyEightButtons

            dm_config = config.get("dm_games")
            games = dm_config.get("GAMES", {}) or dm_config.get("games", {})
            game_config = games.get("2048", {}) or games.get("Twenty Forty Eight", {})
            view = TwentyFortyEightButtons(
                game_id, client, config, game_config, dm_config, user_id,
                test_mode=False, saved_state=game_state,
            )
            view.player_id = user_id
            return view

        if game_type == "tictactoe":
            from games.dm.tictactoe import TicTacToeButtons

            dm_config = config.get("dm_games")
            games = dm_config.get("GAMES", {}) or dm_config.get("games", {})
            game_config = games.get("TicTacToe", {})
            view = TicTacToeButtons(
                game_id, client, config, game_config,
                test_mode=False, saved_state=game_state,
            )
            view.player_id = user_id
            return view

        if game_type == "connectfour":
            from games.dm.connect_four import ConnectFourButtons

            dm_config = config.get("dm_games")
            games = dm_config.get("GAMES", {}) or dm_config.get("games", {})
            game_config = games.get("Connect Four", {})
            view = ConnectFourButtons(
                game_id, client, config, game_config,
                test_mode=False, saved_state=game_state,
            )
            view.player_id = user_id
            return view

        if game_type == "memory":
            from games.dm.memory import MemoryButtons

            dm_config = config.get("dm_games")
            games = dm_config.get("GAMES", {}) or dm_config.get("games", {})
            game_config = games.get("Memory", {})
            view = MemoryButtons(
                game_id, client, config, game_config, dm_config,
                test_mode=False, saved_state=game_state,
            )
            view.player_id = user_id
            return view

        if game_type == "minesweeper":
            from games.dm.minesweeper import MinesweeperButtons, MinesweeperState

            board = game_state.get("board", [[0 for _ in range(5)] for _ in range(5)])
            mine_positions = game_state.get("mine_positions", [])
            num_mines = len(mine_positions) if mine_positions else 4
            dm_config = config.get("dm_games")
            games = dm_config.get("GAMES", {}) or dm_config.get("games", {})
            game_config = games.get("Minesweeper", {})
            state = MinesweeperState(
                game_id=game_id,
                board=board,
                mine_positions=mine_positions,
                num_mines=num_mines,
                bot=client,
                config=config,
                game_config=game_config,
                test_mode=False,
                saved_state=game_state,
            )
            state.player_id = user_id

            message1_id = game_state.get("message1_id")
            message2_id = game_state.get("message2_id")
            if message1_id and message2_id:
                try:
                    user = await client.fetch_user(user_id)
                    channel = user.dm_channel or await user.create_dm()
                    state.message1 = await channel.fetch_message(message1_id)
                    state.message2 = await channel.fetch_message(message2_id)
                    state.message1_id = message1_id
                    state.message2_id = message2_id
                except Exception as e:
                    log_tasks.debug(
                        f"Could not restore Minesweeper message refs for game {game_id}: {e}"
                    )

            view_top = MinesweeperButtons(state, row_offset=0)
            view_bottom = MinesweeperButtons(state, row_offset=5)
            state.view_top = view_top
            state.view_bottom = view_bottom
            return [view_top, view_bottom]

        if game_type == "hangman":
            from games.dm.hangman import HangmanButtons

            word = game_state.get("word", "")
            if not word:
                db = await DatabasePool.get_instance()
                rows = await db.execute(
                    "SELECT word FROM users_hangman WHERE game_id = %s AND user_id = %s",
                    (game_id, user_id),
                )
                if rows and len(rows) > 0:
                    word = rows[0].get("word", "")

            if not word:
                log_tasks.error(f"Could not restore Hangman game {game_id} - word not found")
                return None

            dm_config = config.get("dm_games")
            games = dm_config.get("GAMES", {}) or dm_config.get("games", {})
            game_config = games.get("Hangman", {})
            view = HangmanButtons(
                game_id, client, config, game_config, dm_config, word, user_id,
                test_mode=False, saved_state=game_state,
            )
            view.player_id = user_id
            return view

    except Exception as e:
        log_tasks.error(f"Error creating view for {game_type} game {game_id}: {e}")
        log_tasks.error(traceback.format_exc())
        return None


async def restore_chat_game_timer(
    client, game_id: int, game_name: str, end_time: int, remaining_time: float
) -> None:
    try:
        if remaining_time > 0:
            await asyncio.sleep(remaining_time)

        db = await DatabasePool.get_instance()
        try:
            await db.execute(
                "UPDATE games SET status = 'Finished' WHERE game_id = %s",
                (game_id,),
            )
        except Exception:
            pass

        if client.game_manager:
            try:
                await client.game_manager.end_chat_game(game_id)
            except Exception:
                pass

    except Exception as e:
        log_tasks.error(f"Error in chat game timer for game {game_id}: {e}")
        log_tasks.error(traceback.format_exc())
