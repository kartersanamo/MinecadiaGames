from Assets.leveling_manager import LevelingManager
from Assets.functions import get_data, execute, get_last_game_id, dm_games, dm_games_checks
from discord.ext import commands
import datetime
import discord
import random
import math


class _2048(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client: commands.Bot = client
        self.data: dict = get_data()
        self.game_id: int = 0


class Start2048(discord.ui.View):
    def __init__(self, old_interaction: discord.Interaction):
        super().__init__(timeout=None)
        self.data: dict = get_data()
        self.old_interaction: discord.Interaction = old_interaction
        self._2048: dict = get_data('2048')

    @discord.ui.button(label="Click Here to Play!", style=discord.ButtonStyle.grey, custom_id="play_2048")
    async def play_2048(self, interaction: discord.Interaction, Button: discord.ui.Button) -> None:
        last_game_id: int = await dm_games_checks('2048', self.old_interaction)
        await interaction.response.defer()
        if last_game_id:
            game_embed = discord.Embed(
                title=f"2048 #{last_game_id}",
                description="Welcome to 2048! Begin by choosing a position below!",
                color=discord.Color.from_str(self.data["EMBED_COLOR"])
            )
            game_embed.add_field(name="Score", value="0")
            game_embed.add_field(name="Moves", value="0")
            game_embed.set_footer(text=self.data["FOOTER"], icon_url=self.data["LOGO"])
            await interaction.user.send(embed=game_embed, view=_2048Buttons())

            current_unix: int = int(float(datetime.datetime.now(datetime.timezone.utc).timestamp()))
            await execute(f"INSERT INTO users_2048 (game_id, user_id, status, score, moves, ended_at, started_at) VALUES ({last_game_id}, {interaction.user.id}, 'Started', 0, 0, 0, {current_unix})")
            dm_games.info(f"2048 ({interaction.user.name}#{interaction.user.discriminator})")


class _2048Buttons(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout = None)
        self.board = [[0 for _ in range(4)] for _ in range(4)]
        self.score: int = 0
        self.score_change: int = 0
        self.moves: int = 0
        self.game_id: int = 0
        self.spawn_tile()
        self.spawn_tile()
        self.update_buttons()
        self.cooldowns: dict = {}
        self._2048_data: dict = get_data("2048")

    def calculate_xp(self) -> int:
        if self.score < 256: return 0
        elif self.score < 2000: xp = 50 + ((self.score - 256) / (2000 - 256)) * (120 - 50)
        elif self.score < 4000: xp = 120 + ((self.score - 2000) / (120 - 2000)) * (200 - 120)
        else: xp = 200
        return round(xp)

    async def update_embed(self, interaction: discord.Interaction) -> discord.Embed:
        embed: discord.Embed = interaction.message.embeds[0]
        embed.set_field_at(0, name = "Score", value = f"{self.score} `(+{self.score_change})`")
        embed.set_field_at(1, name = "Moves", value = str(self.moves))
        return embed

    def spawn_tile(self):
        empty = [(r, c) for r in range(4) for c in range(4) if self.board[r][c] == 0]
        if not empty:
            return
        r, c = random.choice(empty)
        self.board[r][c] = 4 if random.random() < 0.1 else 2

    async def can_move(self):
        for r in range(4):
            for c in range(4):
                if self.board[r][c] == 0:
                    return True
                if c < 3 and self.board[r][c] == self.board[r][c+1]:
                    return True
                if r < 3 and self.board[r][c] == self.board[r+1][c]:
                    return True
        return False

    async def move(self, direction):
        moved = False
        score_change: int = 0
        for i in range(4):
            if direction in ('left', 'right'):
                line = self.board[i]
                if direction == 'right':
                    line = line[::-1]
                new_line, score_gain = await self.merge_line(line)
                if direction == 'right':
                    new_line = new_line[::-1]
                if self.board[i] != new_line:
                    self.board[i] = new_line
                    moved = True
                score_change += score_gain
            else:
                line = [self.board[r][i] for r in range(4)]
                if direction == 'down':
                    line = line[::-1]
                new_line, score_gain = await self.merge_line(line)
                if direction == 'down':
                    new_line = new_line[::-1]
                for r in range(4):
                    if self.board[r][i] != new_line[r]:
                        self.board[r][i] = new_line[r]
                        moved = True
                score_change += score_gain
        if moved:
            self.moves += 1
        self.score_change = score_change
        self.score += self.score_change
        return moved

    async def merge_line(self, line):
        new_line = [i for i in line if i != 0]
        score_gain = 0
        i = 0
        while i < len(new_line) - 1:
            if new_line[i] == new_line[i+1]:
                new_line[i] *= 2
                score_gain += new_line[i]
                del new_line[i+1]
                new_line.append(0)
                i += 1
            else:
                i += 1
        new_line += [0] * (4 - len(new_line))
        return new_line, score_gain

    async def end_game(self, interaction: discord.Interaction, lost=False):
        await interaction.response.defer()
        if lost:
            await interaction.channel.send(f"`❌` Sorry {interaction.user.mention}, you ran out of moves!")
        else:
            xp = self.calculate_xp()
            if xp:
                await interaction.channel.send(f"`✅` Congratulations {interaction.user.mention}! You ended the game with `{xp}xp`.")
            else:
                await interaction.channel.send(f"`❌` Sorry {interaction.user.mention}! You did not gain enough score to win XP!")

        if xp:
            lvl_mng = LevelingManager(user=interaction.user, channel=interaction.message.channel, client=interaction.client, xp=xp, source="2048")
            await lvl_mng.update()

        await self.disable_all_items()
        await interaction.message.edit(view=self)

    async def check_cooldown(self, interaction: discord.Interaction, direction: str):
        user_id = interaction.user.id
        if not self.game_id:
            try:
                game_id: int = int(interaction.message.embeds[0].title.split('2048 #')[1])
                self.game_id = game_id
            except:
                return
        last_game_id: int = int(await get_last_game_id('2048'))
        if self.game_id != last_game_id:
            await interaction.response.send_message("`❌` Sorry, but this game has already ended. Please go to the leveling channel to begin another one!", ephemeral = True)
        elif user_id in self.cooldowns and datetime.datetime.now(datetime.timezone.utc) < self.cooldowns[user_id]:
            remaining_time = (self.cooldowns[user_id] - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
            await interaction.response.send_message(f"❌ You need to wait {remaining_time:.2f} seconds before using this button again.", ephemeral = True)
        else:
            self.cooldowns[user_id] = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds = self._2048_data['BUTTON_COOLDOWN'])
            await self.handle_click(interaction, direction)

    async def handle_click(self, interaction: discord.Interaction, direction: str) -> None:
        if await self.move(direction):
            self.spawn_tile()
            self.update_buttons()
            embed = await self.update_embed(interaction)
            if not await self.can_move():
                await self.end_game(interaction, lost=True)
            else:
                await interaction.response.edit_message(view = self, embed = embed)
        else:
            await interaction.response.defer()

    def update_buttons(self):
        self.clear_items()
        for r in range(4):
            for c in range(4):
                value = self.board[r][c]
                label = str(value) if value != 0 else '\u200b'
                style = discord.ButtonStyle.gray
                button = discord.ui.Button(label=label, style=style, disabled=True, row=r, custom_id=f"tile_{r}_{c}")
                self.add_item(button)

        directions = [('⬅️', 'left'), ('⬆️', 'up'), ('⬇️', 'down'), ('➡️', 'right')]
        for emoji, direction in directions:
            button = discord.ui.Button(
                emoji=emoji,
                style=discord.ButtonStyle.blurple,
                row=4,
                custom_id=f"2048_{direction}"  
            )

            async def callback(interaction, dir = direction):
                await self.check_cooldown(interaction = interaction, direction = dir)

            button.callback = callback
            self.add_item(button)

        quit_button = discord.ui.Button(
            emoji="❌",
            style=discord.ButtonStyle.blurple,
            row=4,
            custom_id="2048_quit"
        )

        async def quit_callback(interaction: discord.Interaction):
            await self.end_game(interaction, lost = False)

        quit_button.callback = quit_callback
        self.add_item(quit_button)

    async def disable_all_items(self):
        for item in self.children:
            item.disabled = True


async def setup(client: commands.Bot) -> None:
    await client.add_cog(_2048(client))
