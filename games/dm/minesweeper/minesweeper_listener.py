from typing import Dict
import discord
from discord.ext import commands
from repositories.game_session_repository import GameSessionRepository
from core.logging.setup import get_logger
from games.dm.minesweeper.minesweeper_buttons import MinesweeperButtons
from games.dm.minesweeper.minesweeper_state import MinesweeperState
ROWS, COLS = 10, 5
TOTAL_CELLS = ROWS * COLS  # 50
TEST_MINESWEEPER_GAMES: Dict[int, dict] = {}  # user_id -> {'state': {...}, 'message1_id': int, 'message2_id': int}
class MinesweeperListener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.minesweeper_game = None
        self.logger = get_logger("DMGames")
    
    def set_minesweeper_game(self, minesweeper_game):
        self.minesweeper_game = minesweeper_game
    
    @commands.Cog.listener("on_message")
    async def on_message(self, message: discord.Message):
        if not isinstance(message.channel, discord.DMChannel) or message.author.bot:
            return
        
        if not self.minesweeper_game:
            return
        
        # Check for flag command: "flag [row] [col]" or "flag row col"
        content = message.content.strip().lower()
        if content.startswith('flag '):
            parts = content.split()
            if len(parts) >= 3:
                try:
                    row = int(parts[1]) - 1  # Convert to 0-indexed
                    col = int(parts[2]) - 1  # Convert to 0-indexed
                    
                    if 0 <= row < ROWS and 0 <= col < COLS:
                        try:
                            await message.delete()
                        except (discord.NotFound, discord.Forbidden):
                            pass
                        pos = (row, col)
                        repo = GameSessionRepository()
                        started = await repo.get_started_sessions(message.author.id, "minesweeper")
                        
                        if started:
                            game_id = started[0]["game_id"]
                            try:
                                game_state = await self.bot.app.game_state.load('minesweeper', game_id, message.author.id)
                                if not game_state:
                                    self.logger.warning(f"Minesweeper game state not found for game_id={game_id}")
                                    await message.reply("Game state not found. Try revealing a cell first, or start a new game.", delete_after=5)
                                    return
                                default_board = [[0 for _ in range(COLS)] for _ in range(ROWS)]
                                board = game_state.get('board', default_board)
                                mine_positions = game_state.get('mine_positions', [])
                                num_mines = len(mine_positions) if mine_positions else 4
                                config = self.minesweeper_game.config
                                game_config = self.minesweeper_game.game_config
                                state = MinesweeperState(game_id, board, mine_positions, num_mines, self.bot, self.minesweeper_game.config, game_config, test_mode=False, saved_state=game_state)
                                state.player_id = message.author.id
                                msg1_id = game_state.get('message1_id')
                                msg2_id = game_state.get('message2_id')
                                if msg1_id and msg2_id:
                                    state.message1 = await message.channel.fetch_message(msg1_id)
                                    state.message2 = await message.channel.fetch_message(msg2_id)
                                    state.message1_id = msg1_id
                                    state.message2_id = msg2_id
                                else:
                                    async for ch_msg in message.channel.history(limit=15):
                                        if ch_msg.embeds and "Minesweeper" in (ch_msg.embeds[0].title or "") and f"#{game_id}" in (ch_msg.embeds[0].title or ""):
                                            state.message1 = ch_msg
                                            state.message1_id = ch_msg.id
                                            state.message2 = None
                                            async for nxt in message.channel.history(limit=5, after=ch_msg):
                                                if nxt.author.bot and not nxt.content and not nxt.embeds:
                                                    state.message2 = nxt
                                                    state.message2_id = nxt.id
                                                    break
                                            break
                                if not state.message1 or not state.message2:
                                    await message.reply("Could not find both game messages.", delete_after=5)
                                    return
                                view_top = MinesweeperButtons(state, row_offset=0)
                                view_bottom = MinesweeperButtons(state, row_offset=5)
                                state.view_top = view_top
                                state.view_bottom = view_bottom
                                if pos in state.revealed:
                                    await message.reply("You cannot flag a revealed cell!", delete_after=5)
                                    return
                                if pos in state.flagged:
                                    state.flagged.remove(pos)
                                    await message.reply(f"Unflagged row {row+1}, col {col+1}.", delete_after=5)
                                else:
                                    state.flagged.add(pos)
                                    await message.reply(f"Flagged row {row+1}, col {col+1}.", delete_after=5)
                                await state._save_state()
                                await state.update_both_messages()
                            except Exception as e:
                                self.logger.error(f"Error handling flag command: {e}", exc_info=True)
                                await message.reply("An error occurred while processing the flag command.", delete_after=5)
                        else:
                            test_data = TEST_MINESWEEPER_GAMES.get(message.author.id)
                            if test_data:
                                try:
                                    game_state = test_data.get('state')
                                    msg1_id = test_data.get('message1_id')
                                    msg2_id = test_data.get('message2_id')
                                    if not game_state or not msg1_id or not msg2_id:
                                        await message.reply("Test game state not found. Try revealing a cell first.", delete_after=5)
                                        return
                                    state = MinesweeperState(-999999, game_state.get('board', [[0]*COLS for _ in range(ROWS)]), game_state.get('mine_positions', []), len(game_state.get('mine_positions', [])) or 4, self.bot, self.minesweeper_game.config, self.minesweeper_game.game_config, test_mode=True, saved_state=game_state)
                                    state.player_id = message.author.id
                                    state.message1 = await message.channel.fetch_message(msg1_id)
                                    state.message2 = await message.channel.fetch_message(msg2_id)
                                    state.message1_id = msg1_id
                                    state.message2_id = msg2_id
                                    view_top = MinesweeperButtons(state, row_offset=0)
                                    view_bottom = MinesweeperButtons(state, row_offset=5)
                                    state.view_top = view_top
                                    state.view_bottom = view_bottom
                                    if pos in state.revealed:
                                        await message.reply("You cannot flag a revealed cell!", delete_after=5)
                                        return
                                    if pos in state.flagged:
                                        state.flagged.remove(pos)
                                        await message.reply(f"Unflagged row {row+1}, col {col+1}.", delete_after=5)
                                    else:
                                        state.flagged.add(pos)
                                        await message.reply(f"Flagged row {row+1}, col {col+1}.", delete_after=5)
                                    await state._save_state()
                                    await state.update_both_messages()
                                except discord.NotFound:
                                    TEST_MINESWEEPER_GAMES.pop(message.author.id, None)
                                    await message.reply("Your test game messages were not found. Start a new test game.", delete_after=5)
                                except Exception as e:
                                    self.logger.error(f"Error handling flag command (test): {e}", exc_info=True)
                                    await message.reply("An error occurred.", delete_after=5)
                            else:
                                await message.reply("You don't have an active Minesweeper game!", delete_after=5)
                    else:
                        await message.reply(f"Invalid row/column! Row 1–{ROWS}, col 1–{COLS}.", delete_after=5)
                except ValueError:
                    await message.reply("Invalid format! Use: `flag [row] [col]` (e.g., `flag 1 2`)", delete_after=5)
            else:
                await message.reply("Invalid format! Use: `flag [row] [col]` (e.g., `flag 1 2`)", delete_after=5)
