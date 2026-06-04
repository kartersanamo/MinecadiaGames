import discord
from games.dm.hangman import Hangman


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