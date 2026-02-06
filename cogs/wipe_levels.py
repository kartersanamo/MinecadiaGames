import pandas as pd
import time
import json
import os
from datetime import datetime, timezone
from discord.ext import commands
from discord import app_commands
import discord
from core.config.manager import ConfigManager
from core.database.pool import DatabasePool
from core.logging.setup import get_logger


class WipeLevels(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = ConfigManager.get_instance()
        self.logger = get_logger("Commands")
    
    def _check_admin(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            return False
        
        admin_roles = self.config.get('config', 'ADMIN_ROLES', [])
        user_roles = [role.name for role in interaction.user.roles]
        
        if "*" in admin_roles:
            return True
        
        return any(role in admin_roles for role in user_roles)
    
    async def get_number(self) -> int:
        db = await DatabasePool.get_instance()
        rows = await db.execute("SELECT COUNT(*) as count FROM tickets")
        return int(rows[0]['count']) + 1
    
    @app_commands.command(name="wipe-levels", description="Wipes the levels of all users")
    @app_commands.describe(month="The current month and year EX: 'December 2024'")
    async def wipe_levels(self, interaction: discord.Interaction, month: str):
        if not self._check_admin(interaction):
            await interaction.response.send_message("`❌` You don't have permission to use this command.", ephemeral=True)
            return
        
        if interaction.guild is None:
            return await interaction.response.send_message(
                content="Commands cannot be ran in DMs!",
                ephemeral=True
            )
        
        await interaction.response.send_message(
            content="⚠️ Wiping levels... Please standby as this could take a few seconds"
        )
        
        category = self.bot.get_channel(self.config.get('config', 'DISCORD_TICKETS'))
        if not category:
            await interaction.edit_original_response(content="`❌` Tickets category not found!")
            return
        
        db = await DatabasePool.get_instance()
        top_10_rows = await db.execute(
            "SELECT * FROM leveling ORDER BY CAST(xp AS UNSIGNED) DESC LIMIT 10"
        )
        
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
        
        # Support both old (winners) and new (rewards) structure
        winners = self.config.get('winners', {}) or self.config.get('rewards', {})
        
        try:
            permissions = category.overwrites if hasattr(category, 'overwrites') else {}
            for index, row in enumerate(top_10_rows):
                reward = winners.get('Rewards', {}).get(str(index + 1), '').split('» ')[-1]
                user = interaction.guild.get_member(int(row['user_id']))
                if not user:
                    await interaction.followup.send(f"❌ Could not find user with ID {row['user_id']}")
                    continue
                
                name = index_to_place.get(index)
                if not name:
                    continue
                
                channel = await interaction.guild.create_text_channel(
                    category=category,
                    name=name,
                    overwrites=permissions
                )
                await channel.set_permissions(user, view_channel=True, send_messages=True)
                
                number = await self.get_number()
                await db.execute_insert(
                    "INSERT INTO tickets (channelID, ownerID, type, opened_at, number, active, closed_by, closed_at, reason, name, transcript, privated) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (str(channel.id), str(user.id), 'Discord Leveling Rewards', int(time.time()), number, 'True', ' ', ' ', ' ', ' ', ' ', 'Admin')
                )
                
                embed = discord.Embed(
                    color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR')),
                    description=(
                        f"Hey {user.mention}!\n \nYou have created a new ticket!\n"
                        f"**Type:** Discord Leveling Rewards\n \n"
                        f"**Congratulations on winning leveling for {month}!**\n"
                        f"**Reward:** {reward}\n"
                        f"Your time frame to claim these rewards ends in <t:{int(time.time()) + 604800}:R>. "
                        f"If this time comes, your ticket will be closed without warning.\n\n"
                        f"**One of our staff members will be with you shortly.**"
                    )
                )
                from utils.helpers import get_embed_logo_url
                logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
                embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
                await channel.send(content=user.mention)
                await channel.send(embed=embed)
        except Exception as e:
            return await interaction.edit_original_response(content=f"❌ Failed to create a new ticket! {e}")
        
        try:
            rows = await db.execute("SELECT * FROM leveling")
            data_frame = pd.DataFrame(rows)
            temp_file = "leveling.csv"
            data_frame.to_csv(temp_file, index=False)
            
            admin_logs = self.bot.get_channel(self.config.get('config', 'ADMIN_LOGS'))
            if admin_logs:
                log_embed = discord.Embed(
                    title="Discord Leveling Wiped",
                    description=(
                        f"`Member` {interaction.user.mention} | {interaction.user.name}#{interaction.user.discriminator}\n"
                        f"`Month` {month}\n"
                        f"`Winners` {', '.join(f'<@{key}>' for key in top_users.keys())}"
                    ),
                    color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR')),
                    timestamp=datetime.now(timezone.utc)
                )
                log_embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else None)
                from utils.helpers import get_embed_logo_url
                logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
                log_embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
                files = [discord.File("leveling.csv")]
                if logo_url and logo_url.startswith("attachment://") and not self.config.get('config', 'LOGO').startswith(("http://", "https://")):
                    files.append(discord.File(self.config.get('config', 'LOGO')))
                msg_log = await admin_logs.send(embed=log_embed, files=files)
                os.remove("leveling.csv")
        except Exception as e:
            return await interaction.edit_original_response(content=f"❌ Failed to export the leveling data to admin logs! {e}")
        
        try:
            await db.execute("UPDATE leveling SET xp = 0, level = 1")
        except Exception as e:
            return await interaction.edit_original_response(content=f"❌ Failed to reset the leveling data! {e}")
        
        try:
            from pathlib import Path
            winners_file = str(Path(__file__).parent.parent / "assets" / "Configs" / "winners.json")
            with open(winners_file, "r+") as file:
                data = json.load(file)
                new_month_data = {month: top_users}
                data["Months"] = {**new_month_data, **data.get("Months", {})}
                file.seek(0)
                json.dump(data, file, indent=4)
                file.truncate()
        except Exception as e:
            return await interaction.edit_original_response(content=f"❌ Failed to update the winners data in winners.json! {e}")
        
        role = interaction.guild.get_role(1191076547113799771)
        if role:
            for member in role.members:
                await member.remove_roles(role, reason="New month of winners...")
        
        # Award milestone to 1st place winner
        if top_10_rows:
            first_place_user_id = int(top_10_rows[0]['user_id'])
            try:
                from managers.milestones import MilestonesManager
                milestones_manager = MilestonesManager()
                
                # Check if user already has this achievement
                db = await DatabasePool.get_instance()
                existing = await db.execute(
                    "SELECT achievement_id FROM user_achievements WHERE user_id = %s AND achievement_id = %s",
                    (str(first_place_user_id), "monthly_leaderboard_champion")
                )
                
                if not existing:
                    # Award the achievement silently
                    await milestones_manager._award_achievement(
                        db,
                        first_place_user_id,
                        "monthly_leaderboard_champion",
                        {
                            "id": "monthly_leaderboard_champion",
                            "name": "Monthly Leaderboard Champion",
                            "description": "Finish in 1st place on the monthly leveling leaderboard",
                            "emoji": "👑"
                        }
                    )
                    self.logger.info(f"Awarded monthly leaderboard champion milestone to user {first_place_user_id}")
            except Exception as e:
                self.logger.error(f"Error awarding milestone to 1st place winner: {e}")
        
        message = winners.get('Rewards', {}).get('title', '').replace('{month}', month) + "\n"
        for index, row in enumerate(top_10_rows):
            if index in [0, 1, 2]:
                member = interaction.guild.get_member(int(row['user_id']))
                if member and role:
                    await member.add_roles(role)
            message += winners.get('Rewards', {}).get(str(index + 1), '').replace('{user_id}', str(row['user_id'])) + "\n"
        message += winners.get('Rewards', {}).get('footer', '')
        
        await interaction.edit_original_response(
            content=f"✅ Successfully wiped the leveling leaderboards! [Log]({msg_log.jump_url})\n```\n{message}\n```"
        )


async def setup(bot):
    await bot.add_cog(WipeLevels(bot))

