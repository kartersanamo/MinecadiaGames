from Assets.dmgames import DMGames
from Assets.functions import get_data, execute, dm_games
from Assets.paginator import Paginator
from discord.ext import commands, tasks
from discord import app_commands
from typing import Literal
import datetime
import discord
import json
import re


class SendGames(commands.Cog):
  def __init__(self, client: commands.Bot):
    self.client = client
    self.data = get_data()
    with open('MinecadiaGames/Assets/Configs/wordle.json') as file:
        self.wordle_data = json.load(file)
    with open('MinecadiaGames/Assets/Configs/tictactoe.json') as file:
        self.tictactoe_data = json.load(file)
    with open('MinecadiaGames/Assets/Configs/memory.json') as file:
        self.memory_data = json.load(file)

  @commands.Cog.listener()
  async def on_ready(self):
     self.update_leaderboard.start()

  @tasks.loop(minutes = 10)
  async def update_leaderboard(self):
    guild = self.client.get_guild(680569558754656280)
    channel = guild.get_channel(1186036927514812426)
    embed = discord.Embed(color=discord.Color.from_str(self.data['EMBED_COLOR']),
                          title="Leaderboard <:Minecadia:974713467703545907>",
                          description=(await self.get_leaderboard(guild, self.client) + 
                                       '\n'
                                       'Winners are announced on the last day of every month, rewards include Gold, Hype Boxes, Crates, Tags, and more!\n'
                                       '\n'
                                       '**TIP:** Type </level:1179528065643196557> in any channel to view how many levels you have. :gift:'))
    embed.set_thumbnail(url="https://i.imgur.com/i27vCuC.png")
    embed.set_image(url="https://i.imgur.com/SWwMOIT.png")
    async for message in channel.history():
        if message.embeds:
            await message.edit(embed=embed, view=ViewMore())
            break
  
  async def get_active_game(self):
    rows = await execute("SELECT game_name, refreshed_at FROM games WHERE dm_game = TRUE ORDER BY refreshed_at DESC LIMIT 1")
    return rows[0] if rows else None

  @app_commands.command(name="send-games", description="Sends a message prompt.")
  @app_commands.describe(option="The message that you'd wish to send")
  async def sendgames(self, interaction: discord.Interaction, option: Literal["Leveling"]):
    if interaction.guild is None:
        return await interaction.response.send_message(content="Commands cannot be ran in DMs!", ephemeral=True)
    await interaction.response.send_message(content="Sending your message...", ephemeral=True)
    
    info_last_game: dict = await self.get_active_game()
    active: str = info_last_game['game_name']
    last: int = int(info_last_game['refreshed_at'])
    new_dm_game: int = last + 7200
    game_sequence = ["TicTacToe", "Memory", "Wordle", "Connect Four", "2048"]
    rotation_display = " → ".join(f"**{g}**" if g.lower().replace(" ", "") == active.lower().replace(" ", "") else g for g in game_sequence)
    embeds = {
              "Leveling": [
                 {"embed": discord.Embed(color=discord.Color.from_str(self.data['EMBED_COLOR']),
                                         title="What are levels? <:Minecadia:974713467703545907>",
                                         description=('Your level indicates your activity in our Discord. Activity is determined by how often you type in various chats, react to messages, win mini-games, and much more. Spamming chats is prohibited and rewards will be stripped as punishment for doing so.\n'
                                                      '\n'
                                                      '**How do I check my level?**\n'
                                                      'You can check your level by typing </level:1179528065643196557> in any channel that you can type in.\n'
                                                      '\n'
                                                      '**What does my level mean?**\n'
                                                      'Every month the Top 10 most active players in the Discord will receive in game rewards on the server. The leaderboard below updates frequently and displays who our most active players in the Discord are. At the end of the month winners are announced and given their in game reward and the leaderboards resets back to 0.\n'
                                                      '\n'
                                                      '**How do I redeem my reward?**\n'
                                                      'A ticket will automatically be opened for you when the rewards are announced. From there, please provide which rewards you want, what IGN it will be going to, and which server it will be on.\n'
                                                      '\n'
                                                      '**How do I get the Games Notification Role?**\n'
                                                      'You can get notified for every single game that is sent by heading over to https://discord.com/channels/680569558754656280/922146090504032286/1190636859009814598 and clicking on __Roles__. Then, a menu to gain some notification roles will appear. Click the drop down and select __Games__ at the bottom (along with any other roles you want.)\n'
                                                      '\n'
                                                      f'✅ **Active DM Game**: {active}\n'
                                                      f'🚨 **Next DM Game**: <t:{new_dm_game}:R>\n'
                                                      f"-# {rotation_display}")),
                  "view": DMGames(self.client, active),
                  "image": None
                 },
                 {"embed": discord.Embed(color=discord.Color.from_str(self.data['EMBED_COLOR']),
                                         title="Leaderboard <:Minecadia:974713467703545907>",
                                         description=('\n'
                                                      "Winners are announced on the last day of every month, rewards include Gold, Hype Boxes, Crates, Tags, and more!\n"
                                                      '\n'
                                                      '**TIP:** Type </level:1179528065643196557> in any channel to view how many levels you have. :gift:')),
                 "view": ViewMore(),
                  "image": "https://i.imgur.com/SWwMOIT.png"
                }
              ]
    }
    chosen_embed = embeds.get(option, [])
    for embed in chosen_embed:
        embed_obj = embed['embed']
        if embed['image']:
           embed_obj.set_image(url=embed['image'])
        if embed['embed'].title == "Leaderboard <:Minecadia:974713467703545907>":
            embed_obj.description = await self.get_leaderboard(interaction.guild, interaction.client) + embed_obj.description
            embed_obj.set_thumbnail(url="https://i.imgur.com/i27vCuC.png")
        await interaction.channel.send(embed=embed_obj, view=embed['view'])
    await interaction.edit_original_response(content="Successfully sent your message!")
  
  async def get_leaderboard(self, guild: discord.Guild, client: discord.Client):
    rows = await execute("SELECT * FROM `leveling` ORDER BY `xp`+0 DESC LIMIT 10")
    index_to_emoji = {
       1: "<:minecadia_one:1111028062981718026>",
       2: "<:minecadia_two:1111028088546021466>",
       3: "<:minecadia_three:1111028142430228520>",
       4: "<:minecadia_four:1186027785735643216>",
       5: "<:minecadia_five:1186027816156930058>",
       6: "<:minecadia_six:1186027855210106880>",
       7: "<:minecadia_seven:1186027891989938226>",
       8: "<:minecadia_eight:1186027893285986314>",
       9: "<:minecadia_nine:1186027895508963439>",
       10: "<:minecadia_ten:1186027950689239190>"
    }
    description = ""
    for indx, row in enumerate(rows):
        member = guild.get_member(int(row['user_id']))
        if not member:
           continue
        emoji = index_to_emoji.get(indx+1)
        description += f"{emoji} {member.mention} » Level {row['level']}\n"
    description += f"Updated <t:{int(float(datetime.datetime.now(datetime.timezone.utc).timestamp()))}:R>\n"
    return description

  @sendgames.error
  async def sendgames_error(self, interaction: discord.Interaction, error):
    await interaction.edit_original_response(content=error)


class ViewMore(discord.ui.View):
    def __init__(self):
       super().__init__(timeout = None)
       self.winners_data: dict = get_data("winners")
    
    @discord.ui.button(label="View More", emoji="🏆", custom_id="ViewMore", style=discord.ButtonStyle.grey)
    async def view_more(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await interaction.response.send_message(content="Grabbing the rest of the leaderboard...", ephemeral=True)
        rows = await execute("SELECT * FROM `leveling` ORDER BY `xp`+0 DESC")
        data = []
        for row in rows:
            user = interaction.guild.get_member(int(row['user_id']))
            guild = interaction.client.get_guild(680569558754656280)
            user = guild.get_member(int(row['user_id']))
            if not user:
               continue
            data.append(f"{user.mention} » Level {row['level']}")
        if not data:
            data = ["No data found."]
        paginate = Paginator()
        paginate.title = f"Leveling Leaderboard <:Minecadia:974713467703545907>"
        paginate.sep = 10
        paginate.data = data
        paginate.count = True
        paginate.current_page = 2
        await paginate.send(interaction)
    
    @discord.ui.button(label = "Past Winners", emoji = "📊", custom_id = "past_winners", style = discord.ButtonStyle.grey)
    async def past_winners(self, interaction: discord.Interaction, Button: discord.ui.Button):
        await interaction.response.send_message(content = "Grabbing the past winners...", ephemeral = True)
        paginate = Paginator()
        paginate.title = f"Leveling Leaderboard <:Minecadia:974713467703545907>"
        paginate.sep = 1

        data: list = []
        for month in list(self.winners_data['Months'].keys()):
            month_string: str = ""
            month_string += self.winners_data['Message_Formats']['title'].replace("{month}", month)
            month_string += "".join(self.winners_data['Message_Formats'][str(index + 1)].replace("{user_id}", user_id).replace("{level}", str(self.winners_data['Months'][month][user_id])) for index, user_id in enumerate(self.winners_data['Months'][month].keys()))
            data.append(month_string)

        paginate.data = data
        paginate.current_page = 1
        await paginate.send(interaction)


async def setup(client:commands.Bot) -> None:
  await client.add_cog(SendGames(client))