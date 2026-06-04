import discord
from games.dm.twenty_forty_eight import TwentyFortyEight


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
