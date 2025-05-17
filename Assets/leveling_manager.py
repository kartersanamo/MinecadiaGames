from Assets.functions import get_data, admin_log, execute, log_tasks
import datetime
import discord
import json


class LevelingManager():
    def __init__(self, user: discord.Member, channel: discord.TextChannel, client, xp: int, source: str):
        self.user = user
        self.channel = channel
        self.client = client
        self.xp = xp
        self.source = source
        self.stats = {
                "user_id": str(self.user.id), 
                "xp": "0", 
                "level": "0"
            }
        self.data = get_data()
        with open('MinecadiaGames/Assets/Configs/levels.json') as file:
            self.level_data = json.load(file)

    async def update(self):
        stats = await self.get_stats()
        self.stats = stats if stats else self.stats
        await self.add_experience()
        await self.check_level_up()
        embed = discord.Embed(color=discord.Color.from_str(self.data['EMBED_COLOR']),
                              title="Experience Added",
                              description=(f"`Source` {self.source}\n"
                                           f"`User` {self.user.mention} ({self.user.name})\n"
                                           f"`XP` {self.xp}"),
                              timestamp=datetime.datetime.utcnow())
        await admin_log(self.client, embed)
    
    async def get_stats(self):
        rows = await execute(f"SELECT * FROM leveling WHERE `user_id`='{str(self.user.id)}'")
        if rows:
            return rows[0]
        else:
            await execute(f"INSERT INTO `leveling` (user_id, xp, level) VALUES ({str(self.user.id)}, '0', '0')")
            return None

    async def add_experience(self):
        await execute(f"UPDATE `leveling` SET `xp`={int(self.stats['xp'])+self.xp} WHERE `user_id`={str(self.user.id)}")

    async def check_level_up(self):
        next_level = int(self.stats['level'])+1
        required_xp = self.level_data['LEVELS'][str(next_level)]
        if int(self.stats["xp"])+self.xp > required_xp:
            if self.channel.id in self.data['ANNOUNCE_CHANNELS'] or type(self.channel) == discord.DMChannel:
                await self.channel.send(f'{self.user.mention} has leveled up to level **{next_level}**!')
            else:
                try:
                    channel = await self.user.create_dm()
                    await channel.send(f'{self.user.mention} has leveled up to level **{next_level}**!')
                except Exception as e:
                    log_tasks.error(f"Check Level-up Error: {e}")
            await execute(f"UPDATE `leveling` SET `level`={next_level} WHERE `user_id`={str(self.user.id)}")