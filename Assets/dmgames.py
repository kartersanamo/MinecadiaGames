from Assets.functions import get_data
from Cogs.wordle import StartWordle
from Cogs.tictactoe import StartTicTacToe
from Cogs.memory import StartMemory
from Cogs.connect_four import StartConnectFour
from Cogs._2048 import Start2048
import discord
import json
import re


class DMGames(discord.ui.View):
    def __init__(self, client, active_game):
        super().__init__(timeout=None)
        self.client = client
        self.data = get_data()
        self.wordle_data = get_data("wordle")
        self.tictactoe_data = get_data("tictactoe")
        self.memory_data = get_data("memory")
        self.connect_four_data = get_data("connect_four")
        self._2048_data = get_data("2048")
        self.active: str = active_game.lower()

        self.add_item(self.changelog_button())
        self.add_item(self.rewards_button())

        if self.active == "wordle":
            self.add_item(self.wordle_button())
        elif self.active == "tictactoe":
            self.add_item(self.tictactoe_button())
        elif self.active == "memory":
            self.add_item(self.memory_button())
        elif self.active == "connectfour":
            self.add_item(self.connect_four_button())
        elif self.active == "2048":
            self.add_item(self._2048_button())

    def changelog_button(self):
        return discord.ui.Button(
            style=discord.ButtonStyle.url,
            url="https://discord.com/channels/680569558754656280/1191466240909246564",
            label="Changelog",
            emoji="📜",
            row=1
        )

    def wordle_button(self):
        button = discord.ui.Button(
            emoji="<:Letters:1193341151227428964>",
            label="Click Here To Play Wordle",
            style=discord.ButtonStyle.grey,
            custom_id="wordle_button"
        )

        async def callback(interaction: discord.Interaction):
            embed = discord.Embed(
                title="Wordle",
                description="Click the button below to begin a game of Wordle!",
                color=discord.Color.from_str(self.data["EMBED_COLOR"])
            )
            embed.add_field(name="How do I play?", value="To play Wordle, start by choosing a five-letter word for your guess. The objective is to guess the secret word within six attempts. After each guess, the bot will provide feedback by highlighting correct letters in green, misplaced letters in yellow, and incorrect letters in gray, helping you deduce the hidden word. The challenge lies in strategically selecting words based on the feedback to narrow down the possibilities and solve the puzzle.")
            embed.add_field(name = "Key", value = "🟩 = The letter goes here!\n🟨 = The letter is in the word, but not here!\n⬛ = The letter is not in the word!\n\n**Best of luck to you!**", inline = False)
            embed.set_image(url=self.wordle_data['IMAGE'])
            await interaction.response.send_message(embed=embed, ephemeral=True, view=StartWordle(interaction))

        button.callback = callback
        return button

    def tictactoe_button(self):
        button = discord.ui.Button(
            emoji="<:TicTacToe:1193343648755109899>",
            label="Click Here To Play TicTacToe",
            style=discord.ButtonStyle.grey,
            custom_id="tictactoe_button"
        )

        async def callback(interaction: discord.Interaction):
            embed = discord.Embed(
                title="Tic Tac Toe",
                description="Click the button below to begin a game of Tic Tac Toe!",
                color=discord.Color.from_str(self.data["EMBED_COLOR"])
            )
            embed.add_field(name="How do I play?", value="To play TicTacToe, start by clicking any of the 9 buttons in the game panel. The objective is to get three :x:'s in a row. These can either be __Vertically, Horizontally, or Diagonally__. Any way that you can get 3 in a row will work! After each of your moves, the bot will then make his move in an open position. PS: I heard the bot wasn't that good at playing...\n \n**Best of luck to you!**")
            embed.set_image(url=self.tictactoe_data['IMAGE'])
            await interaction.response.send_message(embed=embed, ephemeral=True, view=StartTicTacToe(interaction))

        button.callback = callback
        return button

    def memory_button(self):
        button = discord.ui.Button(
            emoji="🧠",
            label="Click Here To Play Memory",
            style=discord.ButtonStyle.grey,
            custom_id="memory_button"
        )

        async def callback(interaction: discord.Interaction):
            embed = discord.Embed(
                title="Memory",
                description="Click the button below to begin a game of Memory!",
                color=discord.Color.from_str(self.data["EMBED_COLOR"])
            )
            embed.add_field(name="How do I play?", value="The memory game is well... a game of memory. You have a hidden board of emojis that you must match. You have __{self.memory_data['TRIES']}__ fails to match all of the hidden emojis. Begin by clicking on any two spots. If they match, congrats; you get to keep those emojis shown, and XP is granted. If they do not match, then they will be flipped back over, and you lose a \"try\". Try to remember what those emojis were, because you'll need them later!\n \n**Let the best memory win!")
            embed.set_image(url=self.memory_data['IMAGE'])
            await interaction.response.send_message(embed=embed, ephemeral=True, view=StartMemory(interaction))

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
            embed = discord.Embed(
                title="Connect Four",
                description="Click the button below to begin a game of Connect Four!",
                color=discord.Color.from_str(self.data["EMBED_COLOR"])
            )
            embed.add_field(name="How do I play?", value="To play Connect Four, you must connect four of your pieces in a row. Begin by clicking on any row and the bot will follow your play to try to block you. You must get 4 pieces in a row either __Vertically, Horizontally, or Diagonally__. First one to get all 4 in a row, wins. Be careful, I heard the bot is good at this one!\n \n**BEAT THE BOT!**")
            embed.set_image(url=self.connect_four_data['IMAGE'])
            await interaction.response.send_message(embed=embed, ephemeral=True, view=StartConnectFour(interaction))

        button.callback = callback
        return button

    def _2048_button(self):
        button: discord.ui.Button = discord.ui.Button(
            emoji = "📒",
            label = "Click Here To Play 2048",
            style = discord.ButtonStyle.grey,
            custom_id = "2048_button"
        )

        async def callback(interaction: discord.Interaction):
            embed: discord.Embed = discord.Embed(
                title = "2048",
                description = "Click the button below to begin a game",
                color = discord.Color.from_str(self.data["EMBED_COLOR"])
            )
            embed.add_field(name = "How do I play?", value = "To play 2048, the goal is to combine all of your tiles to sum up to a grand total of a 2048 tile. You combine your tiles by shifting them in any direction (Left, Right, Up, or Down.) When clicking on a direction button, **EVERY** tile will attempt to shift that direction as far as it can. If it slides into any tile of the same amount, the two are summed together, eliminating a tile. After each move, a new tile of 2 or 4 is spawned in. Combine to 2048 before you run out of room!\n\n**DON'T YOU JUST LOVE ADDITION?**")
            embed.set_image(url = self._2048_data["IMAGE"])
            await interaction.response.send_message(
                embed = embed,
                ephemeral = True,
                view = Start2048(interaction)
            )

        button.callback = callback
        return button

    def rewards_button(self):
        button = discord.ui.Button(
            emoji="🎁",
            label="Rewards",
            style=discord.ButtonStyle.grey,
            custom_id="rewards_button",
            row=1
        )

        async def callback(interaction: discord.Interaction):
            with open("MinecadiaGames/Assets/Configs/winners.json", 'r+') as file:
                data = json.load(file)
                rewards = {
                    k: re.sub(r"<@\{user_id\}> \u00bb ", "", v)
                    for k, v in data["Rewards"].items()
                    if k not in ["title", "footer"]
                }
                await interaction.response.send_message(content="\n".join(rewards.values()), ephemeral=True)

        button.callback = callback
        return button
