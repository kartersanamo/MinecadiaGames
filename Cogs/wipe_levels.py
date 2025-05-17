from Assets.functions import get_data, execute, log_commands
from discord.ext import commands
from discord import app_commands
import pandas as pd
import datetime
import time
import discord
import json
import os


class WipeLevels(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client
        self.data = get_data()
        self.winners: str = get_data('winners') 

    async def get_number(self):
        row = await execute("SELECT COUNT(*) FROM `tickets`")
        return int(row[0]['COUNT(*)']) + 1

    @app_commands.command(name = "wipe-levels", description = "Wipes the levels of all users")
    @app_commands.describe(month = "The current month and year EX: 'December 2024'")
    async def wipe_levels(self, interaction: discord.Interaction, month: str):
        if interaction.guild is None:
            return await interaction.response.send_message(content="Commands cannot be ran in DMs!", ephemeral=True)
        else:
            await interaction.response.send_message(content = "⚠️ Wiping levels... Please standby as this could take a few seconds")
            category = interaction.client.get_channel(self.data['DISCORD_TICKETS'])
            top_10_rows = await execute("SELECT * FROM `leveling` ORDER BY `xp`+0 DESC LIMIT 10")
            top_users = {str(row["user_id"]): int(row["level"]) for row in top_10_rows}
            index_to_place = {
                0: "1st",
                1: "2nd",
                2: "3rd",
                3: "4th",
                4: "5th",
                5: "6th",
                6: "7th",
                7: "8th",
                8: "9th",
                9: "10th"
            }
            try:
                permissions = category.overwrites
                for index, row in enumerate(top_10_rows):
                    user = interaction.guild.get_member(int(row['user_id']))
                    reward: str = self.winners['Rewards'][str(index + 1)].split('» ')[1]
                    channel = await interaction.guild.create_text_channel(category = category, name = index_to_place.get(index), overwrites = permissions)
                    await channel.set_permissions(user, view_channel = True, send_messages = True)
                    number = await self.get_number()
                    await execute(f"INSERT INTO `tickets` (`channelID`, `ownerID`, `type`, `opened_at`, `number`, `active`, `closed_by`, `closed_at`, `reason`, `name`, `transcript`, `privated`) VALUES ('{channel.id}', '{user.id}', 'Discord Leveling Rewards', '{int(time.time())}', '{number}', 'True', ' ', ' ', ' ', ' ', ' ', 'Admin')")
                    embed = discord.Embed(color = discord.Color.from_str(self.data['EMBED_COLOR']),
                                        description = f"Hey {user.mention}!\n \nYou have created a new ticket!\n**Type:** Discord Leveling Rewards\n \n**Congratulations on winning leveling for {month}!**\n**Reward:** {reward}\nYour time frame to claim these rewards ends in <t:{int(time.time()) + 604800}:R>. If this time comes, your ticket will be closed without warning.\n\n**One of our staff members will be with you shortly.**")
                    await channel.send(content = user.mention)
                    await channel.send(embed = embed)
            except Exception as e:
                return await interaction.edit_original_response(content = (f"❌ Failed to create a new ticket! {e}"))
            try:
                rows = await execute(f"SELECT * FROM `leveling`")
                data_frame = pd.DataFrame(rows)
                temp_file = "leveling.csv"
                data_frame.to_csv(temp_file, index=False)
                admin_logs: discord.TextChannel = interaction.client.get_channel(self.data['ADMIN_LOGS'])
                log_embed = discord.Embed(
                    title = "Discord Leveling Wiped",
                    description = f"`Member` {interaction.user.mention} | {interaction.user.name}#{interaction.user.discriminator}\n`Month` {month}\n`Winners` {', '.join(list(f'<@{key}>' for key in top_users.keys()))}",
                    color = discord.Color.from_str(self.data["EMBED_COLOR"]), 
                    timestamp = datetime.datetime.now(datetime.timezone.utc)
                )
                log_embed.set_thumbnail(url = interaction.user.avatar)
                msg_log: discord.Message = await admin_logs.send(
                    embed = log_embed, 
                    file = discord.File("leveling.csv")
                )
                os.remove("leveling.csv")
            except Exception as e:
                return await interaction.edit_original_response(content = (f"❌ Failed to export the leveling data to admin logs! {e}"))
            try:
                await execute(f"UPDATE `leveling` SET `xp`=0, `level`=1")
            except Exception as e:
                return await interaction.edit_original_response(content = (f"❌ Failed to reset the leveling data! {e}"))

            try:
                with open("MinecadiaGames/Assets/Configs/winners.json", "r+") as file:
                    data = json.load(file)
                    new_month_data = {month: top_users}
                    data["Months"] = {**new_month_data, **data["Months"]} 
                    file.seek(0)
                    json.dump(data, file, indent=4)
                    file.truncate()
            except Exception as e:
                return await interaction.edit_original_response(content=f"❌ Failed to update the winners data in winners.json! {e}")


            message: str = self.winners['Rewards']['title'].replace('{month}', month) + "\n"
            for index, row in enumerate(top_10_rows):
                message += self.winners['Rewards'][str(index + 1)].replace('{user_id}', row['user_id']) + "\n"
            message += self.winners['Rewards']['footer']
            await interaction.edit_original_response(content = f"✅ Successfully wiped the leveling leaderboards! [Log]({msg_log.jump_url})```\n{message}\n```") 

async def setup(client:commands.Bot) -> None:
  await client.add_cog(WipeLevels(client))