import discord
from games.dm.tictactoe import TicTacToe


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
