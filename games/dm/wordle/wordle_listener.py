import random
import asyncio
import os
from datetime import datetime, timezone
import discord
from discord.ext import commands
from managers.leveling import LevelingManager
from core.logging.setup import get_logger
from repositories.game_session_repository import GameSessionRepository


def _wordle_row_from_session(row: dict) -> dict:
    stats = GameSessionRepository.parse_stats(row)
    return {
        "game_id": row["game_id"],
        "user_id": row["user_id"],
        "word": stats.get("word", ""),
        "attempts": stats.get("attempts", 0),
        "started_at": row.get("started_at"),
    }


class WordleListener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.wordle_game = None
        self.logger = get_logger("DMGames")
        self._cleanup_done = False
        self._cleanup_in_progress = set()  # Track games currently being cleaned up to prevent race conditions
        self._guess_locks: dict[int, asyncio.Lock] = {}
        self._last_guess_at: dict[int, datetime] = {}
    
    def _get_guess_lock(self, user_id: int) -> asyncio.Lock:
        if user_id not in self._guess_locks:
            self._guess_locks[user_id] = asyncio.Lock()
        return self._guess_locks[user_id]

    def _get_guess_cooldown(self) -> float:
        if not self.wordle_game:
            return 2.0
        game_config = self.wordle_game.game_config or {}
        cooldown = game_config.get("GUESS_COOLDOWN") or game_config.get("guess_cooldown")
        if cooldown is not None:
            return float(cooldown)
        dm_config = self.wordle_game.dm_config or {}
        return float(dm_config.get("BUTTON_COOLDOWN") or dm_config.get("button_cooldown") or 2.0)

    def _is_on_guess_cooldown(self, user_id: int) -> bool:
        last_guess = self._last_guess_at.get(user_id)
        if not last_guess:
            return False
        return (datetime.now(timezone.utc) - last_guess).total_seconds() < self._get_guess_cooldown()

    def _mark_guess_time(self, user_id: int) -> None:
        self._last_guess_at[user_id] = datetime.now(timezone.utc)

    def _clear_guess_state(self, user_id: int) -> None:
        self._last_guess_at.pop(user_id, None)
        if not self.wordle_game:
            return
        self.wordle_game.guesses.pop(user_id, None)
        self.wordle_game.letter_states.pop(user_id, None)
        self.wordle_game.active_games.pop(user_id, None)
    
    def set_wordle_game(self, wordle_game):
        self.wordle_game = wordle_game
        self.logger.info(f"WordleListener.set_wordle_game: Set wordle_game instance {id(wordle_game)}")
    
    @commands.Cog.listener("on_ready")
    async def on_ready(self):
        """Clean up stale Wordle games on bot startup"""
        if self._cleanup_done:
            return
        
        self._cleanup_done = True
        
        try:
            await self._cleanup_stale_games()
        except Exception as e:
            self.logger.error(f"Error cleaning up stale Wordle games: {e}")
    
    async def _cleanup_stale_games(self):
        """Clean up Wordle games that have been 'Started' for too long (likely stale)"""
        try:
            repo = GameSessionRepository()
            current_unix = int(datetime.now(timezone.utc).timestamp())
            stale_time = current_unix - 86400  # 24 hours ago

            active = await repo.get_active_dm_games()
            rows = [
                g for g in active
                if g.get("game_type") == "wordle" and g.get("started_at", 0) < stale_time
            ]
            
            if rows:
                self.logger.info(f"WordleListener: Found {len(rows)} stale Wordle games to clean up")
                
                for row in rows:
                    game_id = row["game_id"]
                    user_id = row["user_id"]
                    
                    try:
                        await repo.finish_session(
                            game_id, user_id, "wordle", "lost", ended_at=current_unix
                        )
                        
                        # Clean up from active_games if present
                        if self.wordle_game and user_id in self.wordle_game.active_games:
                            game_data = self.wordle_game.active_games[user_id]
                            if game_data.get('game_id') == game_id:
                                del self.wordle_game.active_games[user_id]
                        
                        # Clean up guesses and letter states
                        if self.wordle_game:
                            if user_id in self.wordle_game.guesses:
                                del self.wordle_game.guesses[user_id]
                            if user_id in self.wordle_game.letter_states:
                                del self.wordle_game.letter_states[user_id]
                        
                        self.logger.info(f"WordleListener: Cleaned up stale game {game_id} for user {user_id}")
                    except Exception as e:
                        self.logger.error(f"WordleListener: Error cleaning up game {game_id}: {e}")
                
                self.logger.info(f"WordleListener: Cleaned up {len(rows)} stale Wordle games")
            else:
                self.logger.debug("WordleListener: No stale Wordle games found to clean up")
        except Exception as e:
            self.logger.error(f"WordleListener: Error in _cleanup_stale_games: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
    
    async def on_message(self, message: discord.Message):
        """Handle Wordle guess messages in DMs"""
        # Log all messages to debug (remove once fixed)
        if not message.author.bot:
            pass
            # self.logger.info(f"WordleListener.on_message called: channel_type={type(message.channel).__name__}, user={message.author.id}")
        
        if not isinstance(message.channel, discord.DMChannel) or message.author.bot:
            return
        
        if not self.wordle_game:
            # self.logger.warning("WordleListener: wordle_game is None")
            return

        async with self._get_guess_lock(message.author.id):
            if self._is_on_guess_cooldown(message.author.id):
                return
            await self._handle_wordle_guess(message)

    async def _handle_wordle_guess(self, message: discord.Message):
        """Process a single Wordle guess (must run under the per-user guess lock)."""
        
        #self.logger.info(f"WordleListener: Processing guess from {message.author.id}: {message.content[:20]}")
        
        # Log active_games state for debugging
        #self.logger.info(f"WordleListener: Checking wordle_game instance {id(self.wordle_game)}")
        #self.logger.info(f"WordleListener: active_games keys: {list(self.wordle_game.active_games.keys())}")
        
        # Check active_games FIRST (this includes test games that aren't in database)
        if message.author.id in self.wordle_game.active_games:
            game_data = self.wordle_game.active_games[message.author.id]
            game_id = game_data['game_id']
            word = game_data['word']
            test_mode = game_data.get('test_mode', False)
            self.logger.debug(f"WordleListener: Found game in active_games dict: game_id={game_id}, test_mode={test_mode}, word={word}")
            
            # For test games, we don't query the database - just use attempts from guesses
            if test_mode or game_id == -999999:
                attempts = len(self.wordle_game.guesses.get(message.author.id, []))
                #self.logger.debug(f"WordleListener: Test game detected, using attempts from guesses: {attempts}")
            else:
                repo = GameSessionRepository()
                session = await repo.get_session(game_id, message.author.id, "wordle")
                if session:
                    stats = GameSessionRepository.parse_stats(session)
                    attempts = stats.get("attempts", 0)
                else:
                    attempts = len(self.wordle_game.guesses.get(message.author.id, []))
        else:
            repo = GameSessionRepository()
            
            all_active_games = [
                _wordle_row_from_session(s)
                for s in await repo.get_started_sessions(message.author.id, "wordle")
            ]
            
            #self.logger.debug(f"WordleListener: Database query returned {len(all_active_games) if all_active_games else 0} active games")
            
            if not all_active_games:
                #self.logger.debug(f"WordleListener: No active game found for user {message.author.id} (neither in active_games nor database)")
                return
            
            # Find the most recent Wordle message in the channel and match it to a game
            # This ensures we use the game that the user is actually looking at
            found_game = None
            found_existing_message = None
            most_recent_message_time = None
            games_with_messages = {}  # Track which games have messages: {game_id: message}
            
            # First pass: find all Wordle messages and match them to active games
            async for channel_message in message.channel.history(limit=100):
                if channel_message.embeds and channel_message.author.bot and channel_message.embeds[0].title:
                    title = channel_message.embeds[0].title
                    if "Wordle" in title:
                        # Extract game_id from title (format: "Wordle #12345")
                        try:
                            if "#" in title:
                                msg_game_id = int(title.split("#")[1].strip())
                                # Check if this game_id is in our active games list
                                for game_row in all_active_games:
                                    if game_row['game_id'] == msg_game_id:
                                        # Store this message for this game
                                        if msg_game_id not in games_with_messages or channel_message.created_at > games_with_messages[msg_game_id].created_at:
                                            games_with_messages[msg_game_id] = channel_message
                                        # Use the most recent one as the found game
                                        if most_recent_message_time is None or channel_message.created_at > most_recent_message_time:
                                            found_game = game_row
                                            found_existing_message = channel_message
                                            most_recent_message_time = channel_message.created_at
                                        break
                        except (ValueError, IndexError):
                            continue
            
            # If we found a game with an existing message, use it
            if found_game and found_existing_message:
                game_id = found_game['game_id']
                word = found_game['word']
                attempts = found_game.get('attempts', 0)
                #self.logger.debug(f"WordleListener: Found game in database with existing message: game_id={game_id}, word={word}, attempts={attempts}")
            else:
                # No message found for any active game - mark all games without messages as stale
                current_unix = int(datetime.now(timezone.utc).timestamp())
                for game_row in all_active_games:
                    game_id = game_row['game_id']
                    # Check if this game has a message (we already checked above)
                    if game_id not in games_with_messages:
                        # Mark stale game as Lost
                        cleanup_key = f"{message.author.id}_{game_id}"
                        if cleanup_key not in self._cleanup_in_progress:
                            self._cleanup_in_progress.add(cleanup_key)
                            try:
                                session = await repo.get_session(game_id, message.author.id, "wordle")
                                if session and session.get("status") == "started":
                                    await repo.finish_session(
                                        game_id,
                                        message.author.id,
                                        "wordle",
                                        "lost",
                                        ended_at=current_unix,
                                    )
                                #self.logger.debug(f"WordleListener: Marked stale game {game_id} as Lost (no message found)")
                            except Exception as e:
                                self.logger.error(f"WordleListener: Error marking stale game {game_id} as Lost: {e}")
                            finally:
                                async def cleanup_after_delay():
                                    await asyncio.sleep(1)
                                    self._cleanup_in_progress.discard(cleanup_key)
                                asyncio.create_task(cleanup_after_delay())
                
                # After cleaning up stale games, check if we have any remaining active games with messages
                if games_with_messages:
                    # Use the most recent game that has a message
                    most_recent_game_id = max(games_with_messages.keys(), key=lambda gid: games_with_messages[gid].created_at)
                    for game_row in all_active_games:
                        if game_row['game_id'] == most_recent_game_id:
                            found_game = game_row
                            found_existing_message = games_with_messages[most_recent_game_id]
                            break
                
                if not found_game:
                    remaining_sessions = await repo.get_started_sessions(message.author.id, "wordle")
                    remaining_games = (
                        [_wordle_row_from_session(remaining_sessions[0])] if remaining_sessions else []
                    )
                    
                    if not remaining_games:
                        #self.logger.debug(f"WordleListener: No active games remaining after cleanup for user {message.author.id}")
                        return
                    
                    # Use the most recent remaining game (but it has no message, so it will be marked as stale later)
                    found_game = remaining_games[0]
                    #self.logger.debug(f"WordleListener: Using most recent game after cleanup: game_id={found_game['game_id']}, but no message found")
                
                game_id = found_game['game_id']
                word = found_game['word']
                attempts = found_game.get('attempts', 0)
            
            # Restore to active_games if not already there (this is a real game, not test)
            test_mode = False  # Database games are always real games
            
            # If we didn't find a message, check one more time for this specific game
            if not found_existing_message:
                async for channel_message in message.channel.history(limit=100):
                    if channel_message.embeds and channel_message.author.bot and channel_message.embeds[0].title:
                        title = channel_message.embeds[0].title
                        if "Wordle" in title and f"#{game_id}" in title:
                            found_existing_message = channel_message
                            break
                
                if not found_existing_message:
                    # Check if we're already cleaning up this game (prevent race conditions)
                    cleanup_key = f"{message.author.id}_{game_id}"
                    if cleanup_key in self._cleanup_in_progress:
                        # Another message handler is already cleaning this up - skip to avoid duplicate warnings/logs
                        return
                
                # Mark this game as being cleaned up (prevent concurrent cleanups)
                self._cleanup_in_progress.add(cleanup_key)
                
                try:
                    # Message doesn't exist - mark game as ended
                    # Only log warning if we actually update the row (first time cleanup)
                    current_unix = int(datetime.now(timezone.utc).timestamp())
                    
                    try:
                        session = await repo.get_session(game_id, message.author.id, "wordle")
                        rows_affected = 1 if session and session.get("status") == "started" else 0
                        if rows_affected > 0:
                            await repo.finish_session(
                                game_id,
                                message.author.id,
                                "wordle",
                                "lost",
                                ended_at=current_unix,
                            )
                        if rows_affected > 0:
                            # Successfully updated - log warning only once
                            self.logger.warning(f"WordleListener: Game {game_id} found in database but message not found - marked as Lost ({rows_affected} row(s) updated)")
                        else:
                            pass
                            # Game was already updated by another handler - don't log as warning, just debug
                            # This happens when multiple messages come in rapidly
                            #self.logger.debug(f"WordleListener: Game {game_id} was already cleaned up by another handler (no rows affected)")
                    except Exception as e:
                        self.logger.error(f"WordleListener: Error marking stale game {game_id} as Lost: {e}")
                        import traceback
                        self.logger.error(traceback.format_exc())
                finally:
                    # Remove from cleanup tracking after a short delay to handle rapid messages
                    # This prevents the same game from being checked multiple times within 1 second
                    async def cleanup_after_delay():
                        await asyncio.sleep(1)
                        self._cleanup_in_progress.discard(cleanup_key)
                    asyncio.create_task(cleanup_after_delay())
                
                # Don't restore the game - it's stale
                return
            
            # Message exists, restore the game
            self.wordle_game.active_games[message.author.id] = {
                'game_id': game_id,
                'word': word,
                'channel': None,
                'test_mode': test_mode
            }
            # Initialize guesses and letter states if not already initialized
            if message.author.id not in self.wordle_game.guesses:
                self.wordle_game.guesses[message.author.id] = []
            if message.author.id not in self.wordle_game.letter_states:
                self.wordle_game.letter_states[message.author.id] = {}
            
            # Load words list if empty (needed for validation)
            await self.wordle_game._load_words_list()
        
        if attempts >= 6:
            #self.logger.debug(f"WordleListener: User has already used all 6 attempts")
            return
        
        #self.logger.debug(f"WordleListener: Processing guess: {message.content.strip()}")
        
        guess = message.content.strip().upper()
        #self.logger.info(f"WordleListener: Validating guess '{guess}'")
        
        # Validate guess length and format
        if len(guess) != 5 or not guess.isalpha():
            #self.logger.info(f"WordleListener: Invalid format: len={len(guess)}, isalpha={guess.isalpha()}")
            error = await message.reply(
                "`❌` Failed! That is an invalid word. Please make sure that your word only contains letters and is five letters long!"
            )
            await asyncio.sleep(4)
            try:
                await error.delete()
            except Exception:
                pass
            return
        
        if not await self.wordle_game.check_word(guess):
            self.logger.info(f"WordleListener: '{guess}' is not a valid word in the word list")
            error = await message.reply(
                "`❌` Failed! That is not a valid word. Please try a different word!"
            )
            await asyncio.sleep(4)
            try:
                await error.delete()
            except Exception:
                pass
            return
        
        self._mark_guess_time(message.author.id)
        
        # Get colors for this guess
        colors = self.wordle_game.get_letter_colors(guess, word)
        
        # Store guess
        if message.author.id not in self.wordle_game.guesses:
            self.wordle_game.guesses[message.author.id] = []
        self.wordle_game.guesses[message.author.id].append({
            'word': guess,
            'colors': colors
        })
        
        # Update letter states
        await self.wordle_game.update_letter_states(message.author.id, guess, colors)
        
        # Generate image
        self.logger.info(f"WordleListener: Generating image for user {message.author.id}, game {game_id}")
        image_path = await self.wordle_game.generate_wordle_image(message.author.id, game_id)
        image_file = discord.File(image_path, filename="wordle.png")
        
        found_wordle_message = None
        message_count = 0
        self.logger.info(f"WordleListener: Looking for Wordle message in history (limit=50)")
        async for channel_message in message.channel.history(limit=50):
            message_count += 1
            if channel_message.embeds and channel_message.author.bot:
                try:
                    title = channel_message.embeds[0].title
                    if "Wordle" in title and f"#{game_id}" in title:
                        found_wordle_message = channel_message
                        self.logger.info(f"WordleListener: Found Wordle message with game_id {game_id}")
                        break
                except (IndexError, AttributeError):
                    pass
        
        if not found_wordle_message:
            # Check if we're already cleaning up this game (prevent race conditions)
            cleanup_key = f"{message.author.id}_{game_id}"
            if cleanup_key in self._cleanup_in_progress:
                # Another message handler is already cleaning this up - skip to avoid duplicate warnings/logs
                # Clean up image file before returning
                try:
                    os.remove(image_path)
                except Exception:
                    pass
                return
            
            # Mark this game as being cleaned up
            self._cleanup_in_progress.add(cleanup_key)
            
            try:
                self.logger.warning(f"WordleListener: Could not find Wordle message for game_id {game_id} (searched {message_count} messages) - cleaning up stale game")
                
                # Clean up stale game - mark as lost and remove from active_games
                current_unix = int(datetime.now(timezone.utc).timestamp())
                
                # Only update database for non-test games
                if not test_mode and game_id != -999999:
                    try:
                        repo = GameSessionRepository()
                        session = await repo.get_session(game_id, message.author.id, "wordle")
                        if session and session.get("status") == "started":
                            await repo.finish_session(
                                game_id,
                                message.author.id,
                                "wordle",
                                "lost",
                                ended_at=current_unix,
                            )
                            self.logger.info(
                                f"WordleListener: Marked stale game {game_id} as Lost for user {message.author.id}"
                            )
                        else:
                            self.logger.debug(
                                f"WordleListener: Game {game_id} was already cleaned up by another handler"
                            )
                    except Exception as e:
                        self.logger.error(f"WordleListener: Error cleaning up stale game {game_id}: {e}")
                        import traceback
                        self.logger.error(traceback.format_exc())
                
                # Clean up from active_games and guesses
                if message.author.id in self.wordle_game.active_games:
                    del self.wordle_game.active_games[message.author.id]
                if message.author.id in self.wordle_game.guesses:
                    del self.wordle_game.guesses[message.author.id]
                if message.author.id in self.wordle_game.letter_states:
                    del self.wordle_game.letter_states[message.author.id]
                
                # Notify user about the stale game
                try:
                    await message.reply("`⚠️` Your previous Wordle game message was not found. The game has been ended. Start a new game using `/dm-games` or the DM games panel.", delete_after=10)
                except Exception:
                    pass
            finally:
                # Remove from cleanup tracking after a delay
                async def cleanup_after_delay():
                    await asyncio.sleep(1)
                    self._cleanup_in_progress.discard(cleanup_key)
                asyncio.create_task(cleanup_after_delay())
                
                # Clean up image file after all processing
                try:
                    os.remove(image_path)
                except Exception:
                    pass
            
            # Return after cleanup
            return
        
        try:
            wordle_embed = found_wordle_message.embeds[0]
            new_attempts = attempts + 1
            wordle_embed.description = f"Attempt {new_attempts}/6"
            wordle_embed.set_image(url="attachment://wordle.png")
            
            #self.logger.debug(f"WordleListener: Editing message with new image")
            await found_wordle_message.edit(embed=wordle_embed, attachments=[image_file])
            #self.logger.debug(f"WordleListener: Successfully updated Wordle message")
            
            # Clean up image file after sending
            try:
                os.remove(image_path)
            except Exception:
                pass
        except Exception as e:
            self.logger.error(f"WordleListener: Error editing message: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            # Clean up image file on error
            try:
                os.remove(image_path)
            except Exception:
                pass
            return
        
        # Update database only for non-test games
        if not test_mode and game_id != -999999:
            repo = GameSessionRepository()
            await repo.merge_stats(
                game_id, message.author.id, "wordle", {"attempts": attempts + 1}
            )
        
        if guess == word:
            active = self.wordle_game.active_games.get(message.author.id)
            if not active or active.get("game_id") != game_id:
                return

            self.wordle_game.active_games.pop(message.author.id, None)

            current_unix = int(datetime.now(timezone.utc).timestamp())
            final_attempts = attempts + 1
            xp = random.randint((7 - final_attempts) * 30, (7 - final_attempts) * 40)
            
            if test_mode:
                await message.channel.send(
                    f"`✅` Congratulations {message.author.mention}! You won! You would have earned `{xp}xp`!"
                )
            else:
                repo = GameSessionRepository()
                session = await repo.get_session(game_id, message.author.id, "wordle")
                if not session or session.get("status") != "started":
                    self._clear_guess_state(message.author.id)
                    return

                stats = GameSessionRepository.parse_stats(session)
                await repo.finish_session(
                    game_id,
                    message.author.id,
                    "wordle",
                    "won",
                    stats={**stats, "attempts": final_attempts, "word": word},
                    ended_at=current_unix,
                )

                await message.channel.send(
                    f"`✅` Congratulations {message.author.mention}! You won `{xp}xp`!"
                )
                
                # Check for achievements first
                await self.bot.app.achievements.check_dm_game_win(message.author, "Wordle", message.channel, self.bot)
                
                lvl_mng = LevelingManager(
                    user=message.author,
                    channel=message.channel,
                    client=self.bot,
                    xp=xp,
                    source="Wordle",
                    game_id=game_id
                )
                await lvl_mng.update()
            
            self._clear_guess_state(message.author.id)
        else:
            if attempts == 5:
                # Don't send final image, just send the loss message
                await message.channel.send(
                    f"`❌` Sorry, but you did not guess the word. The correct word was `{word}`."
                )
                
                # Update database only for non-test games
                if not test_mode and game_id != -999999:
                    current_unix = int(datetime.now(timezone.utc).timestamp())
                    await GameSessionRepository().finish_session(
                        game_id, message.author.id, "wordle", "lost", ended_at=current_unix
                    )
                
                # Clean up guesses and letter states
                self._clear_guess_state(message.author.id)
