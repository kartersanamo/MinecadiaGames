from Assets.leveling_manager import LevelingManager
from Assets.functions import get_data, execute, dm_games, dm_games_checks, get_last_game_id
from discord.ext import commands
import datetime
import discord
import asyncio
import random


class Memory(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client: commands.Bot = client
        self.data: dict = get_data()

class StartMemory(discord.ui.View):
    def __init__(self, old_interaction: discord.Interaction):
        super().__init__(timeout = None)
        self.data: dict = get_data()
        self.old_interaction: discord.Interaction = old_interaction
        self.memory_data: dict = get_data('memory')
    
    @discord.ui.button(label="Click Here to Play!", 
                       style=discord.ButtonStyle.grey, 
                       custom_id="play_memory")
    async def play(self, interaction: discord.Interaction, Button: discord.ui.Button):
        last_game_id: int = await dm_games_checks('memory', self.old_interaction)
        if last_game_id:
            game_embed = discord.Embed(
                title = f"Memory #{last_game_id}",
                description = "Welcome to Memory! Begin by clicking on any two buttons below to try to match!",
                color = discord.Color.from_str(self.data["EMBED_COLOR"]))
            game_embed.add_field(name = "Tries Remaining", value = self.memory_data['TRIES'])
            game_embed.set_image(url = self.memory_data['IMAGE'])
            await interaction.user.send(embed = game_embed, view = MemoryButtons())

            current_unix: int = int(float(datetime.datetime.now(datetime.timezone.utc).timestamp()))
            await execute(f"INSERT INTO users_memory (game_id, user_id, won, attempts, matches, started_at, ended_at) VALUES ({last_game_id}, {interaction.user.id}, 'Started', 0, 0, {current_unix}, 0)")

            dm_games.info(f"Memory ({interaction.user.name}#{interaction.user.discriminator})")


class MemoryButtons(discord.ui.View):
    def __init__(self):
        super().__init__(timeout = None)
        self.data: dict = get_data()
        self.memory_data: dict = get_data('memory')
        
        memory_emojis: list[str] = self.memory_data['EMOJIS'] * 2
        random.shuffle(memory_emojis)
        self.map = memory_emojis
        
        self.xp: int = 0
        self.tries: int = self.memory_data['TRIES']
        self.complete: int = 0
        self.mapping: dict = {
            0: self.pos_1,
            1: self.pos_2,
            2: self.pos_3,
            3: self.pos_4,
            4: self.pos_5,
            5: self.pos_6,
            6: self.pos_7,
            7: self.pos_8,
            8: self.pos_9,
            9: self.pos_10,
            10: self.pos_11,
            11: self.pos_12,
            12: self.pos_13,
            13: self.pos_14,
            14: self.pos_15,
            15: self.pos_16,
            16: self.pos_17,
            17: self.pos_18,
            18: self.pos_19,
            19: self.pos_20,
        }
        self.cooldowns: dict = {}
        self.blue: list = []
        self.game_id: int = 0
    
    async def check_cooldown(self, interaction, button_method, position):
        user_id = interaction.user.id
        if not self.game_id:
            try:
                game_id: int = int(interaction.message.embeds[0].title.split('Memory #')[1])
                self.game_id = game_id
            except:
                return
        last_game_id: int = int(await get_last_game_id('memory'))
        if self.game_id != last_game_id:
            await interaction.response.send_message("`❌` Sorry, but this game has already ended. Please go to the leveling channel to begin another one!", ephemeral = True)
        elif user_id in self.cooldowns and datetime.datetime.now(datetime.timezone.utc) < self.cooldowns[user_id]:
            remaining_time = (self.cooldowns[user_id] - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
            await interaction.response.send_message(f"❌ You need to wait {remaining_time:.2f} seconds before using this button again.", ephemeral=True)
        else:
            self.cooldowns[user_id] = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds = self.memory_data['BUTTON_COOLDOWN'])
            await self.handle_click(interaction, button_method, position)

    async def handle_click(self, interaction: discord.Interaction, button, index: int):
        await interaction.response.defer()

        button.disabled = True
        button.style = discord.ButtonStyle.blurple
        button.emoji = self.map[index]
        self.blue.append(button)
        
        new_msg: discord.PartialMessage = await interaction.message.edit(view = self)
        new_msg: discord.Message = await new_msg.fetch()

        if len(self.blue) > 1:
            embed = interaction.message.embeds[0]

            if self.blue[0].emoji == self.blue[1].emoji:
                self.complete += 2
                self.blue[0].style = discord.ButtonStyle.green
                self.blue[1].style = discord.ButtonStyle.green
                self.blue.clear()
                xp = random.randint(self.memory_data['MATCH_XP']['LOWER'], self.memory_data['MATCH_XP']['UPPER'])
                self.xp += xp
                embed.description = embed.description + f"\n`»+ {xp} Experience`"
                await interaction.message.edit(embed = embed, view = self)
                await execute(f"UPDATE users_memory SET matches = matches + 1 WHERE user_id = {interaction.user.id} AND game_id = {self.game_id}")
            else:
                self.tries = self.tries - 1 
                self.blue[0].style = discord.ButtonStyle.red
                self.blue[1].style = discord.ButtonStyle.red
                await interaction.message.edit(view = self)
                embed.set_field_at(index = 0, name = "Tries Remaining", value = self.tries)
                await asyncio.sleep(1)
                for button in self.blue:
                    button.style = discord.ButtonStyle.grey
                    button.disabled = False
                    button.emoji = "<:TicTacToe:1190287916358967327>"
                self.blue.clear()
                await interaction.message.edit(view = self, embed = embed)
                await execute(f"UPDATE users_memory SET attempts = attempts + 1 WHERE user_id = {interaction.user.id} AND game_id = {self.game_id}")
                
                if self.tries < 1:
                    for function in self.mapping.values():
                        function.disabled = True
                    await interaction.message.edit(view = self)
                    if interaction.user.id not in self.cooldowns or datetime.datetime.now(datetime.timezone.utc) > self.cooldowns[interaction.user.id]:
                        lvl_mng = LevelingManager(user = interaction.user, channel = interaction.channel, client = interaction.client, xp = self.xp, source = "Memory")
                        await lvl_mng.update()
                    await interaction.channel.send(f"`✅` Congratulations {interaction.user.mention}! You won `{self.xp}xp`!")
                    current_unix: int = int(float(datetime.datetime.now(datetime.timezone.utc).timestamp()))
                    await execute(f"UPDATE users_memory SET won = 'Won', ended_at = {current_unix} WHERE user_id = {interaction.user.id} AND game_id = {self.game_id}")
                    

        if self.complete > 19:
            xp = random.randint(self.memory_data['WIN_XP']['LOWER'], self.memory_data['WIN_XP']['UPPER'])
            self.xp += xp
            embed.description = embed.description + f"\n`»+ {xp} Experience (Win)`"
            await interaction.message.edit(embed = embed, view = self)
            lvl_mng = LevelingManager(user = interaction.user, channel = interaction.channel, client = interaction.client, xp = self.xp, source = "Memory")
            await lvl_mng.update()
            await interaction.channel.send(f"`✅` Congratulations {interaction.user.mention}! You won `{self.xp}xp`!")
            current_unix: int = int(float(datetime.datetime.now(datetime.timezone.utc).timestamp()))
            await execute(f"UPDATE users_memory SET won = 'Won', ended_at = {current_unix} WHERE user_id = {interaction.user.id} AND game_id = {self.game_id}")

    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="pos_1", style=discord.ButtonStyle.grey, row=0)
    async def pos_1(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await self.check_cooldown(interaction, self.pos_1, 0)

    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="pos_2", style=discord.ButtonStyle.grey, row=0)
    async def pos_2(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await self.check_cooldown(interaction, self.pos_2, 1)

    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="pos_3", style=discord.ButtonStyle.grey, row=0)
    async def pos_3(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await self.check_cooldown(interaction, self.pos_3, 2)

    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="pos_4", style=discord.ButtonStyle.grey, row=0)
    async def pos_4(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await self.check_cooldown(interaction, self.pos_4, 3)

    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="pos_5", style=discord.ButtonStyle.grey, row=0)
    async def pos_5(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await self.check_cooldown(interaction, self.pos_5, 4)

    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="pos_6", style=discord.ButtonStyle.grey, row=1)
    async def pos_6(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await self.check_cooldown(interaction, self.pos_6, 5)

    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="pos_7", style=discord.ButtonStyle.grey, row=1)
    async def pos_7(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await self.check_cooldown(interaction, self.pos_7, 6)
    
    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="pos_8", style=discord.ButtonStyle.grey, row=1)
    async def pos_8(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await self.check_cooldown(interaction, self.pos_8, 7)
    
    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="pos_9", style=discord.ButtonStyle.grey, row=1)
    async def pos_9(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await self.check_cooldown(interaction, self.pos_9, 8)
    
    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="pos_10", style=discord.ButtonStyle.grey, row=1)
    async def pos_10(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await self.check_cooldown(interaction, self.pos_10, 9)

    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="pos_11", style=discord.ButtonStyle.grey, row=2)
    async def pos_11(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await self.check_cooldown(interaction, self.pos_11, 10)

    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="pos_12", style=discord.ButtonStyle.grey, row=2)
    async def pos_12(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await self.check_cooldown(interaction, self.pos_12, 11)
    
    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="pos_13", style=discord.ButtonStyle.grey, row=2)
    async def pos_13(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await self.check_cooldown(interaction, self.pos_13, 12)
    
    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="pos_14", style=discord.ButtonStyle.grey, row=2)
    async def pos_14(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await self.check_cooldown(interaction, self.pos_14, 13)
    
    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="pos_15", style=discord.ButtonStyle.grey, row=2)
    async def pos_15(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await self.check_cooldown(interaction, self.pos_15, 14)

    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="pos_16", style=discord.ButtonStyle.grey, row=3)
    async def pos_16(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await self.check_cooldown(interaction, self.pos_16, 15)
    
    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="pos_17", style=discord.ButtonStyle.grey, row=3)
    async def pos_17(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await self.check_cooldown(interaction, self.pos_17, 16)
    
    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="pos_18", style=discord.ButtonStyle.grey, row=3)
    async def pos_18(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await self.check_cooldown(interaction, self.pos_18, 17)
    
    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="pos_19", style=discord.ButtonStyle.grey, row=3)
    async def pos_19(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await self.check_cooldown(interaction, self.pos_19, 18)
    
    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="pos_20", style=discord.ButtonStyle.grey, row=3)
    async def pos_20(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await self.check_cooldown(interaction, self.pos_20, 19)

async def setup(client:commands.Bot) -> None:
  await client.add_cog(Memory(client))