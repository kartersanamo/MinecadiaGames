from Assets.leveling_manager import LevelingManager
from Assets.functions import get_data, execute, get_last_game_id, dm_games, dm_games_checks
from discord.ext import commands
import datetime
import discord
import asyncio
import random


class Wordle(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client: commands.Bot = client
        self.data: dict = get_data()
        self.game_id: int = 0

    async def check_word(self, message: str) -> bool:
        return message.isalpha() and len(message) == 5

    async def colorize(self, message: str, solution: str) -> str:
        colors = ["", "", "", "", ""]
        for index, letter in enumerate(list(message)):
            if letter == solution[index]:
                colors[index] = "🟩"
                solution = solution.replace(letter, "_", 1)
        for index, letter in enumerate(list(message)):
            if colors[index] == "🟩":
                continue
            if letter in solution:
                colors[index] = "🟨"
                solution = solution.replace(letter, "_", 1)
            else:
                colors[index] = "⬛"

        result = "".join(colors) + "\n" + "‎ ‎ ‎ ‎ ".join(list(message))
        return result

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if type(message.channel) == discord.DMChannel:
            
            found_wordle_message: discord.Message = None
            async for channel_message in message.channel.history():
                if channel_message.embeds and channel_message.author.bot and channel_message.embeds[0].title:
                    if "Wordle" in channel_message.embeds[0].title:
                        found_wordle_message = channel_message
                        break
            if not found_wordle_message:
                return
            
            wordle_embed: discord.Embed = found_wordle_message.embeds[0]
            try:
                game_id: int = int(found_wordle_message.embeds[0].title.split('Wordle #')[1])
                self.game_id = game_id
            except:
                return
            last_game_id: int = int(await get_last_game_id('wordle'))
            if self.game_id != last_game_id:
                return

            wordle_user_stats: list[dict] = await execute(f"SELECT user_id, word, won, attempts FROM users_wordle WHERE user_id = '{message.author.id}' AND game_id = '{self.game_id}'")
            if not wordle_user_stats or wordle_user_stats[0]['won'] != 'Started':
                return
            
            if wordle_user_stats[0]['attempts'] >= 6:
                return
            
            guess: str = message.content.upper()
            is_valid_guess: bool = await self.check_word(guess)
            if not is_valid_guess:
                error = await message.reply("`❌` Failed! That is an invalid word. Please make sure that your word only contains letters, is five letters long, and is a real word!")
                await asyncio.sleep(4)
                return await error.delete()
            
            response = await self.colorize(guess, wordle_user_stats[0]['word'])
            if "Begin by" in wordle_embed.description:
                wordle_embed.description = response
                wordle_embed.set_image(url = None)
            else:
                wordle_embed.description = wordle_embed.description + "\n" + response
            await found_wordle_message.edit(embed = wordle_embed, attachments = [])

            await execute(f"UPDATE users_wordle SET attempts = {wordle_user_stats[0]['attempts'] + 1} WHERE user_id = {message.author.id} AND game_id = '{self.game_id}'")

            if guess == wordle_user_stats[0]['word']:
                current_unix: int = int(float(datetime.datetime.now(datetime.timezone.utc).timestamp()))
                xp = random.randint(((7 - (wordle_user_stats[0]['attempts'] + 1)) * 30), ((7 - (wordle_user_stats[0]['attempts'] + 1)) * 40))
                await message.channel.send(f"`✅` Congratulations {message.author.mention}! You won `{xp}xp`!")
                
                await execute(f"UPDATE users_wordle SET won = 'Won', ended_at = {current_unix} WHERE user_id = '{message.author.id}' AND game_id = '{self.game_id}'")

                lvl_mng = LevelingManager(user = message.author, channel = message.channel, client = self.client, xp = xp, source = "Wordle")
                return await lvl_mng.update()
            else:
                if wordle_user_stats[0]['attempts'] == 5:
                    await message.channel.send(f"`❌` Sorry, but you did not guess the word. The correct word was `{wordle_user_stats[0]['word']}`.")
                    current_unix: int = int(float(datetime.datetime.now(datetime.timezone.utc).timestamp()))
                    await execute(f"UPDATE users_wordle SET won = 'Lost', ended_at = {current_unix} WHERE user_id = '{message.author.id}' AND game_id = '{self.game_id}'")


class StartWordle(discord.ui.View):
    def __init__(self, old_interaction: discord.Interaction):
        super().__init__(timeout = None)
        self.data: dict = get_data()
        self.old_interaction: discord.Interaction = old_interaction
        self.wordle_data = get_data('wordle')

    @discord.ui.button(label = "Click Here to Play!", style = discord.ButtonStyle.grey, custom_id = "play_wordle")
    async def play_wordle(self, interaction: discord.Interaction, Button: discord.ui.Button) -> None:
        last_game_id: int = await dm_games_checks('wordle', self.old_interaction)
        if last_game_id:
            game_embed = discord.Embed(
                title = f"Wordle #{last_game_id}",
                description = "Welcome to Wordle! Begin by typing your guess below!",
                color = discord.Color.from_str(self.data["EMBED_COLOR"])
            )
            game_embed.set_footer(text = self.data["FOOTER"], icon_url = self.data["LOGO"])
            game_embed.set_image(url = self.wordle_data['IMAGE'])
            await interaction.user.send(embed = game_embed)

            with open(self.wordle_data['WORDS_FILE'], 'r') as file:
                words = file.read().splitlines()
                word = random.choice(words).upper()

            current_unix: int = int(float(datetime.datetime.now(datetime.timezone.utc).timestamp()))
            await execute(f"INSERT INTO users_wordle (game_id, user_id, word, attempts, won, ended_at, started_at) VALUES ({last_game_id}, {interaction.user.id}, '{word}', 0, 'Started', 0, {current_unix})")
            dm_games.info(f"Wordle '{word}' ({interaction.user.name}#{interaction.user.discriminator})")


async def setup(client:commands.Bot) -> None:
  await client.add_cog(Wordle(client))