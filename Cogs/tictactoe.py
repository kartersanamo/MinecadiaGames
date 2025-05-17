from Assets.leveling_manager import LevelingManager
from Assets.functions import get_data, execute, dm_games, get_final, get_last_game_id, has_played, can_dm_user, dm_games_checks
from discord.ext import commands
import datetime
import discord
import random


class TicTacToe(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client: commands.Bot = client
        self.data: dict = get_data()


class StartTicTacToe(discord.ui.View):
    def __init__(self, old_interaction: discord.Interaction):
        super().__init__(timeout=None)
        self.old_interaction: discord.Interaction = old_interaction
        self.data: dict = get_data()
        self.tictactoe_data: dict = get_data('tictactoe')

    @discord.ui.button(label="Click Here to Play!", 
                       style=discord.ButtonStyle.grey, 
                       custom_id="play_tic")
    async def play(self, interaction: discord.Interaction, Button: discord.ui.Button):
        last_game_id: int = await dm_games_checks('tictactoe', self.old_interaction)
        if last_game_id:
            game_embed = discord.Embed(
                title = f"TicTacToe #{last_game_id}",
                description = "Welcome to TicTacToe! Begin by clicking on any of the center 9 buttons below!",
                color = discord.Color.from_str(self.data["EMBED_COLOR"])
            )
            game_embed.set_image(url = self.tictactoe_data['IMAGE'])
            await interaction.user.send(embed = game_embed, view = TicTacToeButtons())

            current_unix: int = int(float(datetime.datetime.now(datetime.timezone.utc).timestamp()))
            await execute(f"INSERT INTO users_tictactoe (game_id, user_id, won, ended_at, started_at) VALUES ({last_game_id}, {interaction.user.id}, 'Started', 0, {current_unix})")

            dm_games.info(f"TicTacToe ({interaction.user.name}#{interaction.user.discriminator})")


class TicTacToeButtons(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.button_style_mapping: dict = {
            discord.ButtonStyle.blurple: "C",
            discord.ButtonStyle.grey: "O",
            discord.ButtonStyle.green: "P"
        }
        self.data: dict = get_data()
        self.tictactoe_data: dict = get_data('tictactoe')
        self.game_id: int = 0
        self.cooldowns: dict = {}

    async def handle_win(self, interaction: discord.Interaction, check: str):
        for row in await self.get_open_spaces():
            if row:
                for button in row:
                    button.disabled = True
        current_unix: int = int(float(datetime.datetime.now(datetime.timezone.utc).timestamp()))
        if check == "P":
            xp = random.randint(50, 100)
            await interaction.channel.send(f"`✅` Congratulations {interaction.user.mention}! You won `{xp}xp`!")
            await execute(f"UPDATE users_tictactoe SET won = 'Won', ended_at = {current_unix} WHERE user_id = {interaction.user.id} AND game_id = {self.game_id}")
            lvl_mng = LevelingManager(user = interaction.user, channel = interaction.channel, client = interaction.client, xp = xp, source = "TicTacToe")
            await lvl_mng.update()
        elif check == "C":
            await execute(f"UPDATE users_tictactoe SET won = 'Lost', ended_at = {current_unix} WHERE user_id = {interaction.user.id} AND game_id = {self.game_id}")
            await interaction.channel.send(f"`❌` Sorry {interaction.user.mention}, the bot has beat you in TicTacToe! Come back later to try again!")
        elif check == "Full":
            await execute(f"UPDATE users_tictactoe SET won = 'Tied', ended_at = {current_unix} WHERE user_id = {interaction.user.id} AND game_id = {self.game_id}")
            await interaction.channel.send(f"`🟰` Uh oh {interaction.user.mention}, you and the bot have tied in TicTacToe! Come back later to try again!")

    async def check_cooldown(self, interaction, button_method):
        user_id = interaction.user.id
        game_embed: discord.Embed = interaction.message.embeds[0]
        if not self.game_id:
            try:
                game_id: int = int(game_embed.title.split('TicTacToe #')[1])
                self.game_id = game_id
            except:
                return
        last_game_id: int = int(await get_last_game_id('tictactoe'))
        if self.game_id != last_game_id:
            await interaction.response.send_message("`❌` Sorry, but this game has already ended. Please go to the leveling channel to begin another one!", ephemeral = True)
        elif user_id in self.cooldowns and datetime.datetime.now(datetime.timezone.utc) < self.cooldowns[user_id]:
            remaining_time = (self.cooldowns[user_id] - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
            await interaction.response.send_message(f"❌ You need to wait {remaining_time:.2f} seconds before using this button again.", ephemeral=True)
        else:
            self.cooldowns[user_id] = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds = self.tictactoe_data['BUTTON_COOLDOWN'])
            await self.handle_click(interaction, button_method)

    async def handle_click(self, interaction: discord.Interaction, button):
        await interaction.response.defer()
        button.disabled = True
        button.style = discord.ButtonStyle.green
        button.emoji = "✖️"
        check = await self.check(interaction)
        if not check:
            await self.computer_turn(button)
            await self.check(interaction)
        await interaction.message.edit(view = self, attachments = [])

    async def get_open_spaces(self):
        buttons = [[self.slot_1, self.slot_2, self.slot_3], [self.slot_4, self.slot_5, self.slot_6], [self.slot_7, self.slot_8, self.slot_9]]
        return [[button for button in row if not button.disabled] for row in buttons]

    async def computer_turn(self, user_move):
        open_spaces = await self.get_open_spaces()
        open_spaces = [row for row in open_spaces if row]
        if open_spaces:
            user_row, user_col = self.get_position(user_move)
            adjacent_positions = self.get_adjacent_positions(user_row, user_col)
            valid_moves = [position for row in open_spaces for position in row if self.get_position(position) in adjacent_positions]
            if valid_moves:
                position = random.choice(valid_moves)
            else:
                position = random.choice([button for row in open_spaces for button in row])
            position.disabled = True
            position.style = discord.ButtonStyle.blurple
            position.emoji = "<:TicTacToeCircle:1190296396465701004>"

    def is_valid_position(self, position):
        return position[0] > -1 < 3 and position[1] > -1 < 3

    async def get_board(self):
        buttons = [[self.slot_1, self.slot_2, self.slot_3], [self.slot_4, self.slot_5, self.slot_6], [self.slot_7, self.slot_8, self.slot_9]]
        board = [[self.button_style_mapping.get(button.style) for button in row] for row in buttons]
        return board

    async def check(self, interaction: discord.Interaction):
        board = await self.get_board()
        for row in board:
            if all(cell == row[0] and cell != 'O' for cell in row):
                await self.handle_win(interaction, row[0])
                return True
        for col in range(len(board[0])):
            if all(board[row][col] == board[0][col] and board[row][col] != 'O' for row in range(len(board))):
                await self.handle_win(interaction, board[0][col])
                return True
        if all(board[i][i] == board[0][0] and board[i][i] != 'O' for i in range(len(board))):
            await self.handle_win(interaction, board[0][0])
            return True
        if all(board[i][len(board) - i - 1] == board[0][len(board) - 1] and board[i][len(board) - i - 1] != 'O' for i in range(len(board))):
            await self.handle_win(interaction, board[0][2])
            return True
        open_spaces = await self.get_open_spaces()
        if all(not any(row) for row in open_spaces):
            await self.handle_win(interaction, "Full")
            return True
    
    def get_position(self, button):
        position_map = {
            self.slot_1: (0, 0),
            self.slot_2: (0, 1),
            self.slot_3: (0, 2),
            self.slot_4: (1, 0),
            self.slot_5: (1, 1),
            self.slot_6: (1, 2),
            self.slot_7: (2, 0),
            self.slot_8: (2, 1),
            self.slot_9: (2, 2) 
        }
        return position_map.get(button, None)

    def get_adjacent_positions(self, row, col):
        return [(row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1), (row - 1, col - 1), (row - 1, col + 1), (row + 1, col - 1), (row + 1, col + 1)]

    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="disabled_1", style=discord.ButtonStyle.grey, row=0, disabled=True)
    async def disabled_1(self, interaction: discord.Interaction, Button: discord.ui.Button):
        pass

    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="disabled_2", style=discord.ButtonStyle.grey, row=0, disabled=True)
    async def disabled_2(self, interaction: discord.Interaction, Button: discord.ui.Button):
        pass

    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="disabled_3", style=discord.ButtonStyle.grey, row=0, disabled=True)
    async def disabled_3(self, interaction: discord.Interaction, Button: discord.ui.Button):
        pass

    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="disabled_4", style=discord.ButtonStyle.grey, row=0, disabled=True)
    async def disabled_4(self, interaction: discord.Interaction, Button: discord.ui.Button):
        pass

    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="disabled_5", style=discord.ButtonStyle.grey, row=0, disabled=True)
    async def disabled_5(self, interaction: discord.Interaction, Button: discord.ui.Button):
        pass

    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="disabled_6", style=discord.ButtonStyle.grey, row=1, disabled=True)
    async def disabled_6(self, interaction: discord.Interaction, Button: discord.ui.Button):
        pass

    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="slot_1", style=discord.ButtonStyle.grey, row=1)
    async def slot_1(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await self.check_cooldown(interaction, self.slot_1)
    
    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="slot_2", style=discord.ButtonStyle.grey, row=1)
    async def slot_2(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await self.check_cooldown(interaction, self.slot_2)
    
    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="slot_3", style=discord.ButtonStyle.grey, row=1)
    async def slot_3(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await self.check_cooldown(interaction, self.slot_3)
    
    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="disabled_7", style=discord.ButtonStyle.grey, row=1, disabled=True)
    async def disabled_7(self, interaction: discord.Interaction, Button: discord.ui.Button):
        pass

    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="disabled_8", style=discord.ButtonStyle.grey, row=2, disabled=True)
    async def disabled_8(self, interaction: discord.Interaction, Button: discord.ui.Button):
        pass

    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="slot_4", style=discord.ButtonStyle.grey, row=2)
    async def slot_4(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await self.check_cooldown(interaction, self.slot_4)
    
    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="slot_5", style=discord.ButtonStyle.grey, row=2)
    async def slot_5(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await self.check_cooldown(interaction, self.slot_5)
    
    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="slot_6", style=discord.ButtonStyle.grey, row=2)
    async def slot_6(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await self.check_cooldown(interaction, self.slot_6)
    
    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="disabled_9", style=discord.ButtonStyle.grey, row=2, disabled=True)
    async def disabled_9(self, interaction: discord.Interaction, Button: discord.ui.Button):
        pass

    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="disabled_10", style=discord.ButtonStyle.grey, row=3, disabled=True)
    async def disabled_10(self, interaction: discord.Interaction, Button: discord.ui.Button):
        pass
    
    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="slot_7", style=discord.ButtonStyle.grey, row=3)
    async def slot_7(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await self.check_cooldown(interaction, self.slot_7)
    
    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="slot_8", style=discord.ButtonStyle.grey, row=3)
    async def slot_8(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await self.check_cooldown(interaction, self.slot_8)
    
    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="slot_9", style=discord.ButtonStyle.grey, row=3)
    async def slot_9(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await self.check_cooldown(interaction, self.slot_9)
    
    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="disabled_11", style=discord.ButtonStyle.grey, row=3, disabled=True)
    async def disabled_11(self, interaction: discord.Interaction, Button: discord.ui.Button):
        pass

    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="disabled_12", style=discord.ButtonStyle.grey, row=4, disabled=True)
    async def disabled_12(self, interaction: discord.Interaction, Button: discord.ui.Button):
        pass

    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="disabled_13", style=discord.ButtonStyle.grey, row=4, disabled=True)
    async def disabled_13(self, interaction: discord.Interaction, Button: discord.ui.Button):
        pass

    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="disabled_14", style=discord.ButtonStyle.grey, row=4, disabled=True)
    async def disabled_14(self, interaction: discord.Interaction, Button: discord.ui.Button):
        pass

    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="disabled_15", style=discord.ButtonStyle.grey, row=4, disabled=True)
    async def disabled_15(self, interaction: discord.Interaction, Button: discord.ui.Button):
        pass

    @discord.ui.button(emoji="<:TicTacToe:1190287916358967327>", custom_id="disabled_16", style=discord.ButtonStyle.grey, row=4, disabled=True)
    async def disabled_16(self, interaction: discord.Interaction, Button: discord.ui.Button):
        pass

async def setup(client:commands.Bot) -> None:
  await client.add_cog(TicTacToe(client))