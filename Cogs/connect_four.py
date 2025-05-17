from Assets.leveling_manager import LevelingManager
from Assets.functions import get_data, execute, get_last_game_id, dm_games, dm_games_checks
from PIL import Image
from discord.ext import commands
import datetime
import discord
import asyncio
import random
import math


class ConnectFour(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client: commands.Bot = client
        self.data: dict = get_data()
        self.game_id: int = 0


class StartConnectFour(discord.ui.View):
    def __init__(self, old_interaction: discord.Interaction):
        super().__init__(timeout = None)
        self.data: dict = get_data()
        self.old_interaction: discord.Interaction = old_interaction
        self.connect_four: dict = get_data('connect_four')

    @discord.ui.button(label = "Click Here to Play!", style = discord.ButtonStyle.grey, custom_id = "play_connect_four")
    async def play_connect_four(self, interaction: discord.Interaction, Button: discord.ui.Button) -> None:
        last_game_id: int = await dm_games_checks('connectfour', self.old_interaction)
        await interaction.response.defer()
        if last_game_id:
            game_embed = discord.Embed(
                title = f"Connect Four #{last_game_id}",
                description = "Welcome to Connect Four! Begin by choosing a position below!",
                color = discord.Color.from_str(self.data["EMBED_COLOR"])
            )
            game_embed.add_field(name = "Number of Moves", value = "0")
            game_embed.set_footer(text = self.data["FOOTER"], icon_url = self.data["LOGO"])
            file = discord.File(self.connect_four['base_image_path'], filename = "ConnectFourBoard.png")
            game_embed.set_image(url = "attachment://ConnectFourBoard.png")
            await interaction.user.send(file = file, embed = game_embed, view = ConnectFourButtons())

            current_unix: int = int(float(datetime.datetime.now(datetime.timezone.utc).timestamp()))
            await execute(f"INSERT INTO users_connectfour (game_id, user_id, status, moves, ended_at, started_at) VALUES ({last_game_id}, {interaction.user.id}, 'Started', 0, 0, {current_unix})")
            dm_games.info(f"Connect Four ({interaction.user.name}#{interaction.user.discriminator})")


class ConnectFourButtons(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout = None)
        self.data: dict = get_data()
        self.connect_four: dict = get_data('connect_four')
        self.board: list = [['' for _ in range(7)] for _ in range(6)]
        self.cooldowns: dict = {}
        self.game_id: int = 0
        self.moves: int = 0
        self.map: dict = {
            0: self.pos_1,
            1: self.pos_2,
            2: self.pos_3,
            3: self.pos_4,
            4: self.pos_5,
            5: self.pos_6,
            6: self.pos_7
        }
        self.full: str = []

    async def generate_image(self) -> discord.File:
        base_image_path = self.connect_four["base_image_path"]
        output_image_path = self.connect_four["output_image_path"]
        red_piece_path = self.connect_four["red_piece_path"]
        yellow_piece_path = self.connect_four["yellow_piece_path"]

        with Image.open(base_image_path) as base_image:
            red_piece = Image.open(red_piece_path)
            yellow_piece = Image.open(yellow_piece_path)

            cell_width = 110
            cell_height = 110
            start_x = 101
            start_y = 136
            cell_spacing = 17

            rows = len(self.board)
            cols = len(self.board[0])

            for row in range(rows):
                for col in range(cols):
                    value = self.board[row][col]
                    if value == "R":
                        piece = red_piece
                    elif value == "Y":
                        piece = yellow_piece
                    else:
                        continue

                    x = start_x + col * (cell_width + cell_spacing)
                    y = start_y + row * (cell_height + cell_spacing)

                    piece_resized = piece.resize((cell_width, cell_height), Image.Resampling.LANCZOS)
                    base_image.paste(piece_resized, (x, y), piece_resized)

            base_image.save(output_image_path)

        return discord.File(output_image_path, filename="ConnectFourOutput.png")


    async def get_highest_row(self, column: int) -> int:
        for row in reversed(range(len(self.board))):
            if not self.board[row][column]:
                return row
        return -1  
    
    async def board_full(self) -> None:
        pass

    async def bot_play(self, index: int) -> None:
        max_offset = 6
        initial_offsets = [-1, 0, 1]
        random.shuffle(initial_offsets)
        for delta in initial_offsets:
            position = index + delta
            if 0 <= position <= 6:
                highest_row = await self.get_highest_row(position)
                if highest_row != -1:
                    self.board[highest_row][position] = "Y"
                    
                    if highest_row == 0:
                        button = self.map.get(position)
                        button.disabled = True
                        self.full.append(button.custom_id)

                    return

        for offset in range(2, max_offset + 1):
            offsets = [-offset, offset]
            random.shuffle(offsets)
            for delta in offsets:
                position = index + delta
                if 0 <= position <= 6:
                    highest_row = await self.get_highest_row(position)
                    if highest_row != -1:
                        self.board[highest_row][position] = "Y"

                        if highest_row == 0:
                            button = self.map.get(position)
                            button.disabled = True
                            self.full.append(button.custom_id)

                        return

    async def check_wins(self) -> str:
        rows = len(self.board)
        cols = len(self.board[0])
        directions = [
            (0, 1),
            (1, 0),
            (1, 1),
            (-1, 1)
        ]

        for row in range(rows):
            for col in range(cols):
                current = self.board[row][col]
                if current not in ("R", "Y"):
                    continue

                for dr, dc in directions:
                    try:
                        if all(
                            0 <= row + dr * i < rows and
                            0 <= col + dc * i < cols and
                            self.board[row + dr * i][col + dc * i] == current
                            for i in range(4)
                        ):
                            return current
                    except IndexError:
                        continue

        return None 


    async def update_image(self, interaction: discord.Interaction):
        embed: discord.Embed = interaction.message.embeds[0]
        embed.set_image(url = "attachment://ConnectFourOutput.png")
        embed.set_field_at(
            index = 0, 
            name = "Number of Moves",
            value = self.moves
        )
        image : discord.File = await self.generate_image()
        await self.swap_buttons()
        await interaction.edit_original_response(attachments = [image], embed = embed, view = self)
    
    async def swap_buttons(self) -> None:
        for child in self.children:
            if child.custom_id in self.full: continue
            child.disabled = not child.disabled

    async def disable_all(self) -> None:
        for child in self.children:
            child.disabled = True

    async def calculate_xp(self) -> int:
        min_xp = 50
        max_xp = 150
        decay_rate = 0.1 
        xp = max_xp * math.exp(-decay_rate * (self.moves - 1)) + min_xp
        return round(min(xp, max_xp))

    async def send_winner(self, interaction: discord.Interaction, won: str) -> None:
        if won == "R":
            xp: int = await self.calculate_xp()
            lvl_mng = LevelingManager(user = interaction.user, channel = interaction.message.channel, client = interaction.client, xp = xp, source = "Connect Four")
            await lvl_mng.update()
            await interaction.channel.send(content = f"`✅` Congratulations {interaction.user.mention}! You won `{xp}xp`!")
        elif won == "Y":
            await interaction.channel.send(content = f"`❌` Sorry {interaction.user.mention}! You lost against the bot!")

    async def handle_click(self, interaction: discord.Interaction, button, index: int) -> None:
        await interaction.response.defer()
        highest_row: int = await self.get_highest_row(index)
        self.board[highest_row][index] = "R"
        self.moves += 1
        if highest_row == 0:
            button.disabled = True
            self.full.append(button.custom_id)

        await self.update_image(interaction)
        won: str = await self.check_wins()
        if won:
            await self.disable_all()
            await self.send_winner(interaction, won)
            return
        await self.bot_play(index)
        await asyncio.sleep(1.5)
        await self.update_image(interaction)
        won: str = await self.check_wins()
        if won:
            await self.disable_all()
            await self.send_winner(interaction, won)
            return

    async def check_cooldown(self, interaction, button_method, position):
        user_id = interaction.user.id
        if not self.game_id:
            try:
                game_id: int = int(interaction.message.embeds[0].title.split('Connect Four #')[1])
                self.game_id = game_id
            except:
                return
        last_game_id: int = int(await get_last_game_id('connectfour'))
        if self.game_id != last_game_id:
            await interaction.response.send_message("`❌` Sorry, but this game has already ended. Please go to the leveling channel to begin another one!", ephemeral = True)
        elif user_id in self.cooldowns and datetime.datetime.now(datetime.timezone.utc) < self.cooldowns[user_id]:
            remaining_time = (self.cooldowns[user_id] - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
            await interaction.response.send_message(f"❌ You need to wait {remaining_time:.2f} seconds before using this button again.", ephemeral = True)
        else:
            self.cooldowns[user_id] = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds = self.connect_four['BUTTON_COOLDOWN'])
            await self.handle_click(interaction, button_method, position)


    @discord.ui.button(label = "1", custom_id = "pos_1", style = discord.ButtonStyle.grey, row = 0)
    async def pos_1(self, interaction: discord.Interaction, Button: discord.ui.Button) -> None:
        await self.check_cooldown(interaction, self.pos_1, 0)
    
    @discord.ui.button(label = "2", custom_id = "pos_2", style = discord.ButtonStyle.grey, row = 0)
    async def pos_2(self, interaction: discord.Interaction, Button: discord.ui.Button) -> None:
        await self.check_cooldown(interaction, self.pos_2, 1)
    
    @discord.ui.button(label = "3", custom_id = "pos_3", style = discord.ButtonStyle.grey, row = 0)
    async def pos_3(self, interaction: discord.Interaction, Button: discord.ui.Button) -> None:
        await self.check_cooldown(interaction, self.pos_3, 2)
    
    @discord.ui.button(label = "4", custom_id = "pos_4", style = discord.ButtonStyle.grey, row = 0)
    async def pos_4(self, interaction: discord.Interaction, Button: discord.ui.Button) -> None:
        await self.check_cooldown(interaction, self.pos_4, 3)

    @discord.ui.button(label = "5", custom_id = "pos_5", style = discord.ButtonStyle.grey, row = 1)
    async def pos_5(self, interaction: discord.Interaction, Button: discord.ui.Button) -> None:
        await self.check_cooldown(interaction, self.pos_5, 4)

    @discord.ui.button(label = "6", custom_id = "pos_6", style = discord.ButtonStyle.grey, row = 1)
    async def pos_6(self, interaction: discord.Interaction, Button: discord.ui.Button) -> None:
        await self.check_cooldown(interaction, self.pos_6, 5)

    @discord.ui.button(label = "7", custom_id = "pos_7", style = discord.ButtonStyle.grey, row = 1)
    async def pos_7(self, interaction: discord.Interaction, Button: discord.ui.Button) -> None:
        await self.check_cooldown(interaction, self.pos_7, 6)


async def setup(client:commands.Bot) -> None:
  await client.add_cog(ConnectFour(client))