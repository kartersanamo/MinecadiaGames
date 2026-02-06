import json
import re
import discord
from core.config.manager import ConfigManager
from games.dm.wordle import Wordle
from games.dm.tictactoe import TicTacToe
from games.dm.connect_four import ConnectFour
from games.dm.memory import Memory
from games.dm.twenty_forty_eight import TwentyFortyEight
from games.dm.hangman import Hangman
from utils.helpers import check_dm_game_requirements


class DMGamesView(discord.ui.View):
    def __init__(self, bot, active_game: str):
        super().__init__(timeout=None)
        self.bot = bot
        self.config = ConfigManager.get_instance()
        self.active = active_game.lower()
        
        # Add View More button
        self.add_item(self.view_more_button())
        
        if self.active == "wordle":
            self.add_item(self.wordle_button())
        elif self.active == "tictactoe":
            self.add_item(self.tictactoe_button())
        elif self.active == "memory":
            self.add_item(self.memory_button())
        elif self.active == "connect four":
            self.add_item(self.connect_four_button())
        elif self.active == "2048" or self.active == "twenty forty eight":
            self.add_item(self.twenty_forty_eight_button())
        elif self.active == "minesweeper":
            self.add_item(self.minesweeper_button())
        elif self.active == "hangman":
            self.add_item(self.hangman_button())
    
    def view_more_button(self):
        button = discord.ui.Button(
            label="View More",
            emoji="📊",
            style=discord.ButtonStyle.grey,
            custom_id="view_more_leaderboard",
            row=1
        )
        
        async def callback(interaction: discord.Interaction):
            try:
                await interaction.response.defer(ephemeral=True)
                
                from utils.paginator import Paginator
                from ui.sendgames_view import SendGamesView
                from core.logging.setup import get_logger
                from core.config.manager import ConfigManager
                
                logger = get_logger("UI")
                config = ConfigManager.get_instance()
                
                # Send loading message first
                loading_embed = discord.Embed(
                    title="Full Leaderboard <:minecadia_2:1444800686372950117>",
                    description="⏳ Loading leaderboard data... Please wait.",
                    color=discord.Color.from_str(config.get('config', 'EMBED_COLOR'))
                )
                from utils.helpers import get_embed_logo_url
                logo_url = get_embed_logo_url(config.get('config', 'LOGO'))
                loading_embed.set_footer(text=config.get('config', 'FOOTER'), icon_url=logo_url)
                loading_msg = await interaction.followup.send(embed=loading_embed, ephemeral=True, wait=True)
                
                # Get full leaderboard
                leaderboard_data = await SendGamesView.get_full_leaderboard(interaction.guild, interaction.client)
                
                if not leaderboard_data:
                    error_embed = discord.Embed(
                        title="Full Leaderboard <:minecadia_2:1444800686372950117>",
                        description="No leaderboard data available.",
                        color=discord.Color.from_str(config.get('config', 'EMBED_COLOR'))
                    )
                    from utils.helpers import get_embed_logo_url
                    logo_url = get_embed_logo_url(config.get('config', 'LOGO'))
                    error_embed.set_footer(text=config.get('config', 'FOOTER'), icon_url=logo_url)
                    await loading_msg.edit(embed=error_embed)
                    return
                
                paginator = Paginator()
                paginator.title = "Full Leaderboard <:minecadia_2:1444800686372950117>"
                paginator.data = leaderboard_data
                paginator.sep = 20  # 20 entries per page
                paginator.ephemeral = True  # Mark as ephemeral
                
                # Edit the loading message with the actual paginator
                embed = paginator.create_embed()
                paginator.update_buttons()
                await loading_msg.edit(embed=embed, view=paginator)
            except Exception as e:
                logger.error(f"Error in View More button callback: {e}")
                import traceback
                logger.error(traceback.format_exc())
                try:
                    if interaction.response.is_done():
                        await interaction.followup.send("`❌` An error occurred while loading the leaderboard. Please try again later.", ephemeral=True)
                    else:
                        await interaction.response.send_message("`❌` An error occurred while loading the leaderboard. Please try again later.", ephemeral=True)
                except:
                    pass
        
        button.callback = callback
        return button
    
    def wordle_button(self):
        button = discord.ui.Button(
            emoji="<:Letters:1193341151227428964>",
            label="Click Here To Play Wordle",
            style=discord.ButtonStyle.grey,
            custom_id="wordle_button"
        )
        
        async def callback(interaction: discord.Interaction):
            can_play, game_id, error = await check_dm_game_requirements(interaction, 'wordle', self.config)
            if not can_play:
                await interaction.response.send_message(f"`❌` {error}", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="Wordle",
                description="Click the button below to begin a game of Wordle!",
                color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR'))
            )
            embed.add_field(
                name="How do I play?",
                value="To play Wordle, start by choosing a five-letter word for your guess. The objective is to guess the secret word within six attempts. After each guess, the bot will provide feedback by highlighting correct letters in green, misplaced letters in yellow, and incorrect letters in gray, helping you deduce the hidden word. The challenge lies in strategically selecting words based on the feedback to narrow down the possibilities and solve the puzzle."
            )
            embed.add_field(
                name="Key",
                value="🟩 = The letter goes here!\n🟨 = The letter is in the word, but not here!\n⬛ = The letter is not in the word!\n\n**Best of luck to you!**",
                inline=False
            )
            wordle_config = self.config.get('wordle', {})
            embed.set_image(url=wordle_config.get('IMAGE'))
            from utils.helpers import get_embed_logo_url
            logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
            embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
            
            view = StartWordleView(interaction, self.bot)
            # Register the view so the button works
            self.bot.add_view(view)
            await interaction.response.send_message(embed=embed, ephemeral=True, view=view)
        
        button.callback = callback
        return button
    
    def tictactoe_button(self):
        button = discord.ui.Button(
            emoji="<:TicTacToe:1193343648755109899>",
            label="Click Here To Play TicTacToe",
            style=discord.ButtonStyle.grey,
            custom_id="tictactoe_button"
        )
        button.callback = self.tictactoe_callback
        return button
    
    async def tictactoe_callback(self, interaction: discord.Interaction):
        from core.logging.setup import get_logger
        logger = get_logger("UI")
        try:
            can_play, game_id, error = await check_dm_game_requirements(interaction, 'tictactoe', self.config)
            if not can_play:
                await interaction.response.send_message(f"`❌` {error}", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="Tic Tac Toe",
                description="Click the button below to begin a game of Tic Tac Toe!",
                color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR'))
            )
            embed.add_field(
                name="How do I play?",
                value="To play TicTacToe, start by clicking any of the 9 buttons in the game panel. The objective is to get three :x:'s in a row. These can either be __Vertically, Horizontally, or Diagonally__. Any way that you can get 3 in a row will work! After each of your moves, the bot will then make his move in an open position. PS: I heard the bot wasn't that good at playing...\n \n**Best of luck to you!**"
            )
            # Support both old and new structure
            tictactoe_config = self.config.get('tictactoe', {})
            if not tictactoe_config:
                dm_config = self.config.get('dm_games', {})
                games = dm_config.get('games', {}) or dm_config.get('GAMES', {})
                tictactoe_config = games.get('TicTacToe', {})
            image_url = tictactoe_config.get('IMAGE') or tictactoe_config.get('image_url')
            if image_url:
                embed.set_image(url=image_url)
            from utils.helpers import get_embed_logo_url
            logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
            embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
            
            view = StartTicTacToeView(interaction, self.bot)
            # Register the view so the button works
            self.bot.add_view(view)
            await interaction.response.send_message(embed=embed, ephemeral=True, view=view)
        except Exception as e:
            from core.logging.setup import get_logger
            logger = get_logger("UI")
            logger.error(f"Error in TicTacToe button callback: {e}")
            import traceback
            logger.error(traceback.format_exc())
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "`❌` An error occurred while starting the game. Please try again later.",
                        ephemeral=True
                    )
            except:
                try:
                    await interaction.followup.send(
                        "`❌` An error occurred while starting the game. Please try again later.",
                        ephemeral=True
                    )
                except:
                    pass
    
    def memory_button(self):
        button = discord.ui.Button(
            emoji="🧠",
            label="Click Here To Play Memory",
            style=discord.ButtonStyle.grey,
            custom_id="memory_button"
        )
        
        async def callback(interaction: discord.Interaction):
            can_play, game_id, error = await check_dm_game_requirements(interaction, 'memory', self.config)
            if not can_play:
                await interaction.response.send_message(f"`❌` {error}", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="Memory",
                description="Click the button below to begin a game of Memory!",
                color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR'))
            )
            # Support both old and new structure
            memory_config = self.config.get('memory', {})
            if not memory_config:
                dm_config = self.config.get('dm_games', {})
                games = dm_config.get('games', {}) or dm_config.get('GAMES', {})
                memory_config = games.get('Memory', {})
            tries = memory_config.get('TRIES') or memory_config.get('max_tries', 7)
            image_url = memory_config.get('IMAGE') or memory_config.get('image_url')
            embed.add_field(
                name="How do I play?",
                value=f"The memory game is well... a game of memory. You have a hidden board of emojis that you must match. You have __{tries}__ fails to match all of the hidden emojis. Begin by clicking on any two spots. If they match, congrats; you get to keep those emojis shown, and XP is granted. If they do not match, then they will be flipped back over, and you lose a \"try\". Try to remember what those emojis were, because you'll need them later!\n \n**Let the best memory win!**"
            )
            embed.set_image(url=image_url)
            from utils.helpers import get_embed_logo_url
            logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
            embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
            
            view = StartMemoryView(interaction, self.bot)
            # Register the view so the button works
            self.bot.add_view(view)
            await interaction.response.send_message(embed=embed, ephemeral=True, view=view)
        
        button.callback = callback
        return button
    
    def connect_four_button(self):
        button = discord.ui.Button(
            emoji="❌",
            label="Click Here To Play Connect Four",
            style=discord.ButtonStyle.grey,
            custom_id="connect_four_button"
        )
        
        async def callback(interaction: discord.Interaction):
            can_play, game_id, error = await check_dm_game_requirements(interaction, 'connect four', self.config)
            if not can_play:
                await interaction.response.send_message(f"`❌` {error}", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="Connect Four",
                description="Click the button below to begin a game of Connect Four!",
                color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR'))
            )
            embed.add_field(
                name="How do I play?",
                value="To play Connect Four, you must connect four of your pieces in a row. Begin by clicking on any row and the bot will follow your play to try to block you. You must get 4 pieces in a row either __Vertically, Horizontally, or Diagonally__. First one to get all 4 in a row, wins. Be careful, I heard the bot is good at this one!\n \n**BEAT THE BOT!**"
            )
            # Support both old and new structure
            connect_four_config = self.config.get('connect_four', {})
            if not connect_four_config:
                dm_config = self.config.get('dm_games', {})
                games = dm_config.get('games', {}) or dm_config.get('GAMES', {})
                connect_four_config = games.get('Connect Four', {})
            image_url = connect_four_config.get('IMAGE') or connect_four_config.get('image_url')
            embed.set_image(url=image_url)
            from utils.helpers import get_embed_logo_url
            logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
            embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
            
            view = StartConnectFourView(interaction, self.bot)
            # Register the view so the button works
            self.bot.add_view(view)
            await interaction.response.send_message(embed=embed, ephemeral=True, view=view)
        
        button.callback = callback
        return button
    
    def twenty_forty_eight_button(self):
        button = discord.ui.Button(
            emoji="🔢",
            label="Click Here To Play 2048",
            style=discord.ButtonStyle.grey,
            custom_id="2048_button"
        )
        
        async def callback(interaction: discord.Interaction):
            can_play, game_id, error = await check_dm_game_requirements(interaction, '2048', self.config)
            if not can_play:
                await interaction.response.send_message(f"`❌` {error}", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="2048",
                description="Click the button below to begin a game of 2048!",
                color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR'))
            )
            embed.add_field(
                name="How do I play?",
                value="2048 is a puzzle game where you combine numbered tiles on a 4x4 grid. Use the direction buttons (⬆️⬇️⬅️➡️) to move all tiles in that direction. When two tiles with the same number touch, they merge into one with double the value! Your goal is to reach the **2048** tile. The game ends when the board is full and no moves are possible. Try to get the highest score possible!\n\n**Good luck!**"
            )
            from utils.helpers import get_embed_logo_url
            logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
            embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
            
            view = Start2048View(interaction, self.bot)
            # Register the view so the button works
            self.bot.add_view(view)
            await interaction.response.send_message(embed=embed, ephemeral=True, view=view)
        
        button.callback = callback
        return button
    
    def minesweeper_button(self):
        button = discord.ui.Button(
            emoji="💣",
            label="Click Here To Play Minesweeper",
            style=discord.ButtonStyle.grey,
            custom_id="minesweeper_button"
        )
        
        async def callback(interaction: discord.Interaction):
            can_play, game_id, error = await check_dm_game_requirements(interaction, 'minesweeper', self.config)
            if not can_play:
                await interaction.response.send_message(f"`❌` {error}", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="Minesweeper",
                description="Click the button below to begin a game of Minesweeper!",
                color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR'))
            )
            embed.add_field(
                name="How do I play?",
                value="Minesweeper is a puzzle game where you reveal cells on a 5x5 grid. Some cells contain mines - click on one and you lose! Numbers show how many mines are adjacent to that cell. Use the flag button to mark suspected mines. Reveal all non-mine cells to win!\n\n**Good luck!**",
                inline=False
            )
            from utils.helpers import get_embed_logo_url
            logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
            embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
            
            view = StartMinesweeperView(interaction, self.bot)
            # Register the view so the button works
            self.bot.add_view(view)
            await interaction.response.send_message(embed=embed, ephemeral=True, view=view)
        
        button.callback = callback
        return button
    
    def hangman_button(self):
        button = discord.ui.Button(
            emoji="🎯",
            label="Click Here To Play Hangman",
            style=discord.ButtonStyle.grey,
            custom_id="hangman_button"
        )
        
        async def callback(interaction: discord.Interaction):
            can_play, game_id, error = await check_dm_game_requirements(interaction, 'hangman', self.config)
            if not can_play:
                await interaction.response.send_message(f"`❌` {error}", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="Hangman",
                description="Click the button below to begin a game of Hangman!",
                color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR'))
            )
            # Support both old and new structure
            dm_config = self.config.get('dm_games', {})
            games = dm_config.get('games', {}) or dm_config.get('GAMES', {})
            hangman_config = games.get('Hangman', {})
            max_wrong = hangman_config.get('MAX_WRONG') or hangman_config.get('max_wrong_guesses', 6)
            image_url = hangman_config.get('IMAGE') or hangman_config.get('image_url')
            embed.add_field(
                name="How do I play?",
                value=f"Hangman is a classic word-guessing game! A secret word has been chosen, and you need to guess letters one at a time. You have __{max_wrong}__ wrong guesses before the game ends. Each correct guess reveals that letter in the word, while each wrong guess adds a part to the hangman drawing. Guess all the letters before running out of wrong guesses to win!\n \n**Guess wisely!**"
            )
            if image_url:
                embed.set_image(url=image_url)
            from utils.helpers import get_embed_logo_url
            logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
            embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
            
            view = StartHangmanView(interaction, self.bot)
            # Register the view so the button works
            self.bot.add_view(view)
            await interaction.response.send_message(embed=embed, ephemeral=True, view=view)
        
        button.callback = callback
        return button


class StartWordleView(discord.ui.View):
    def __init__(self, old_interaction: discord.Interaction, bot):
        super().__init__(timeout=None)
        self.old_interaction = old_interaction
        self.bot = bot
    
    @discord.ui.button(label="Click Here to Play!", style=discord.ButtonStyle.grey, custom_id="play_wordle")
    async def play(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = Wordle(self.bot)
        success = await game.run(interaction.user, 'wordle')
        if success:
            await interaction.response.send_message(
                "`✅` Successfully started a game of Wordle in your DMs!",
                ephemeral=True
            )
        else:
            error_msg = game.last_error or "Failed to start game. Please try again later."
            await interaction.response.send_message(
                f"`❌` {error_msg}",
                ephemeral=True
            )


class StartTicTacToeView(discord.ui.View):
    def __init__(self, old_interaction: discord.Interaction, bot):
        super().__init__(timeout=None)
        self.old_interaction = old_interaction
        self.bot = bot
    
    @discord.ui.button(label="Click Here to Play!", style=discord.ButtonStyle.grey, custom_id="play_tic")
    async def play(self, interaction: discord.Interaction, button: discord.ui.Button):
        from core.logging.setup import get_logger
        logger = get_logger("UI")
        try:
            await interaction.response.defer(ephemeral=True)
            game = TicTacToe(self.bot)
            success = await game.run(interaction.user, 'tictactoe')
            if success:
                await interaction.followup.send(
                    "`✅` Successfully started a game of TicTacToe in your DMs!",
                    ephemeral=True
                )
            else:
                error_msg = game.last_error or "Failed to start game. Please try again later."
                await interaction.followup.send(
                    f"`❌` {error_msg}",
                    ephemeral=True
                )
        except Exception as e:
            logger.error(f"Error in StartTicTacToeView play: {e}")
            import traceback
            logger.error(traceback.format_exc())
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "`❌` An error occurred while starting the game. Please try again later.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "`❌` An error occurred while starting the game. Please try again later.",
                        ephemeral=True
                    )
            except:
                pass


class StartMemoryView(discord.ui.View):
    def __init__(self, old_interaction: discord.Interaction, bot):
        super().__init__(timeout=None)
        self.old_interaction = old_interaction
        self.bot = bot
    
    @discord.ui.button(label="Click Here to Play!", style=discord.ButtonStyle.grey, custom_id="play_memory")
    async def play(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = Memory(self.bot)
        success = await game.run(interaction.user, 'memory')
        if success:
            await interaction.response.send_message(
                "`✅` Successfully started a game of Memory in your DMs!",
                ephemeral=True
            )
        else:
            error_msg = game.last_error or "Failed to start game. Please try again later."
            await interaction.response.send_message(
                f"`❌` {error_msg}",
                ephemeral=True
            )


class StartConnectFourView(discord.ui.View):
    def __init__(self, old_interaction: discord.Interaction, bot):
        super().__init__(timeout=None)
        self.old_interaction = old_interaction
        self.bot = bot
    
    @discord.ui.button(label="Click Here to Play!", style=discord.ButtonStyle.grey, custom_id="play_connect_four")
    async def play(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = ConnectFour(self.bot)
        success = await game.run(interaction.user, 'connect four')
        if success:
            await interaction.response.send_message(
                "`✅` Successfully started a game of Connect Four in your DMs!",
                ephemeral=True
            )
        else:
            error_msg = game.last_error or "Failed to start game. Please try again later."
            await interaction.response.send_message(
                f"`❌` {error_msg}",
                ephemeral=True
            )


class Start2048View(discord.ui.View):
    def __init__(self, old_interaction: discord.Interaction, bot):
        super().__init__(timeout=None)
        self.old_interaction = old_interaction
        self.bot = bot
    
    @discord.ui.button(label="Click Here to Play!", style=discord.ButtonStyle.grey, custom_id="play_2048")
    async def play(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = TwentyFortyEight(self.bot)
        success = await game.run(interaction.user, '2048')
        if success:
            await interaction.response.send_message(
                "`✅` Successfully started a game of 2048 in your DMs!",
                ephemeral=True
            )
        else:
            error_msg = game.last_error or "Failed to start game. Please try again later."
            await interaction.response.send_message(
                f"`❌` {error_msg}",
                ephemeral=True
            )


class StartMinesweeperView(discord.ui.View):
    def __init__(self, old_interaction: discord.Interaction, bot):
        super().__init__(timeout=None)
        self.old_interaction = old_interaction
        self.bot = bot
    
    @discord.ui.button(label="Click Here to Play!", style=discord.ButtonStyle.grey, custom_id="play_minesweeper")
    async def play(self, interaction: discord.Interaction, button: discord.ui.Button):
        from games.dm.minesweeper import Minesweeper
        game = Minesweeper(self.bot)
        success = await game.run(interaction.user, 'minesweeper')
        if success:
            await interaction.response.send_message(
                "`✅` Successfully started a game of Minesweeper in your DMs!",
                ephemeral=True
            )
        else:
            error_msg = game.last_error or "Failed to start game. Please try again later."
            await interaction.response.send_message(
                f"`❌` {error_msg}",
                ephemeral=True
            )


class StartHangmanView(discord.ui.View):
    def __init__(self, old_interaction: discord.Interaction, bot):
        super().__init__(timeout=None)
        self.old_interaction = old_interaction
        self.bot = bot
    
    @discord.ui.button(label="Click Here to Play!", style=discord.ButtonStyle.grey, custom_id="play_hangman")
    async def play(self, interaction: discord.Interaction, button: discord.ui.Button):  
        game = Hangman(self.bot)
        success = await game.run(interaction.user, 'hangman')
        if success:
            await interaction.response.send_message(
                "`✅` Successfully started a game of Hangman in your DMs!",
                ephemeral=True
            )
        else:
            error_msg = game.last_error or "Failed to start game. Please try again later."
            await interaction.response.send_message(
                f"`❌` {error_msg}",
                ephemeral=True
            )