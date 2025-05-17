import datetime
import aiomysql
import discord
import logger
import json
import time

# Variables that represent loggers that can be accessed anywhere in the bot's code simply by importing the logger
# Then you can run i.e `log_tasks.info("...")` to log information under the logger of "Tasks"
log_tasks = logger.logging.getLogger("Tasks")
log_commands = logger.logging.getLogger("Commands")
chat_games = logger.logging.getLogger("Chat Games")
dm_games = logger.logging.getLogger("DM Games")

def get_data(config: str = "config"):
   with open(f"MinecadiaGames/Assets/Configs/{config}.json", "r") as file:
      return json.load(file)

data = get_data()

def task(action_name: str, log: bool = None):
    """
    A decorator function that measures the execution time of a given function and logs the results.

    Parameters:
    - action_name (str): The name of the action being performed by the decorated function.
    - log (bool, optional): A flag indicating whether to log the execution time. Defaults to None.

    Returns:
    - A decorator function that wraps the input function and logs the execution time.

    The decorator function logs the start time of the decorated function, executes it, measures the execution time,
    and logs the result (success or failure) along with the execution time. If the execution time exceeds 2 seconds,
    a warning message is logged.
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                time_elapsed = round((time.perf_counter() - start_time), 2)
                if time_elapsed > 3:
                    log_tasks.warning(f"{action_name} took a long time to complete and finished in {time_elapsed}s")
                elif log:
                    log_tasks.info(f"{action_name} completed in {time_elapsed}s")
                return result
            except Exception as error:
                log_tasks.error(f"{action_name} failed after {str(round((time.perf_counter() - start_time), 2))}s : {error}")
                raise error
        return wrapper
    return decorator

async def connect():
    return await aiomysql.connect(
        host=data["DATABASE_CONFIG"]["host"],
        port=data["DATABASE_CONFIG"]["port"],
        user=data["DATABASE_CONFIG"]["user"],
        password=data["DATABASE_CONFIG"]["password"],
        db=data["DATABASE_CONFIG"]["database"],
        autocommit=bool(data["DATABASE_CONFIG"]["autocommit"]),
        cursorclass=aiomysql.DictCursor
    )

async def execute(query):
    rows = []
    connection = None 
    try:
        connection = await connect()
        async with connection.cursor() as cursor:
            await cursor.execute(query)
            rows = await cursor.fetchall()
    except Exception as error:
        log_tasks.error(f"Execute error {error}")
    finally:
        if connection:
            connection.close()
        return rows

async def get_final(name, data):
    rows = await execute(f"SELECT MAX(`refreshed_at`) FROM dm_games WHERE game_name = '{name}'")
    last_time = int(rows[0]['MAX(`refreshed_at`)'] if rows else 0)
    return last_time + data['COOLDOWN']

async def admin_log(client, embed: discord.Embed):
    guild = client.get_guild(data['GUILD_ID'])
    channel = guild.get_channel(data['LOGS_CHANNEL'])
    await channel.send(embed=embed)

async def has_played(game: str, user_id: int, last_game_id: int) -> bool:
    rows: list[dict] = await execute(f"SELECT user_id FROM users_{game.lower()} WHERE game_id = {last_game_id}")
    return user_id in [row['user_id'] for row in rows]

async def get_last_dm_game_info() -> dict:
    rows = await execute(f"SELECT game_name, game_id FROM games WHERE dm_game = {True} ORDER BY game_id DESC LIMIT 1")
    return rows[0]if rows else None

async def get_last_game_id(game: str) -> int:
    rows = await execute(f"SELECT game_id FROM games WHERE game_name = '{game}' ORDER BY game_id DESC LIMIT 1")
    return rows[0]['game_id'] if rows else None

async def can_dm_user(user: discord.User) -> bool:
    try:
        await user.send()
    except discord.Forbidden:
        return False
    except discord.HTTPException:
        return True

async def dm_games_checks(game: str, interaction: discord.Interaction):
    embed = discord.Embed(
            description = f"🎮 Attempting to start a game of {game} for {interaction.user.mention}",
            color = discord.Color.from_str(data["EMBED_COLOR"])
    )
    await interaction.edit_original_response(embed = embed, view = None)
    
    verified_role: discord.Role = interaction.guild.get_role(data["VERIFIED_ROLE"])
    if verified_role not in interaction.user.roles:
        embed.description = f"❌ Failed! You need the {verified_role.mention} role in order to play games!"
        await interaction.edit_original_response(embed = embed)
        return False
    
    last_game_info: dict = await get_last_dm_game_info()
    last_game_id: int = last_game_info['game_id']
    last_game_name: str = last_game_info['game_name']
    if last_game_name.lower() != game.lower():
        embed.description = f"❌ This is not the most recent game. You can only play the most recently refreshed game!"
        await interaction.edit_original_response(embed = embed)
        return False
    
    played: bool = await has_played(game, interaction.user.id, last_game_id)
    if played:
        embed.description = f"❌ Failed! You have already started {game.title()} game `#{last_game_id}`"
        await interaction.edit_original_response(embed = embed)
        return False
    
    user_can_be_dmd: bool = await can_dm_user(interaction.user)
    if not user_can_be_dmd:
        embed.description = f"❌ Failed! I cannot send you a DM! You must have your DMs enabled to play {game.title()}!"
        await interaction.edit_original_response(embed = embed)
        return False
    
    embed.description = f"✅ Successfully started a game of {game.title()} in your DMs!"
    await interaction.edit_original_response(embed = embed)
    
    return last_game_id

#async def refresh_dm_game(client, game: str, data):
#    dm_games.info(f"Refreshing {game.title()}...")
#    game = game.title()
#    guild: discord.Guild = client.get_guild(680569558754656280)
#    leveling_channel: discord.Channel = guild.get_channel(1186036927514812426)
#    games_role: discord.Role = guild.get_role(1190635899025891398)
#    refreshed_at: int = int(float(datetime.datetime.now(datetime.timezone.utc).timestamp()))
#    await execute(f"INSERT INTO dm_games (game_name, refreshed_at) VALUES ('{game}', '{refreshed_at}')")
#    async for message in leveling_channel.history():
#        if "🚨" in message.content:
#            await message.delete()
#        elif message.embeds and message.author.bot:
#            if len(message.components[0].children) > 2:
#                embed: discord.Embed = message.embeds[0]
#                old_unix: str = embed.description.split('\n\n')[-1].split(f'{game.title()} ')[1].split('\n')[0]
#                next_unix: int = await get_final(game, data)
#                embed.description = embed.description.replace(old_unix, f"<t:{next_unix}:R>")
#                await message.edit(embed = embed)
#                break
#    
#    await leveling_channel.send(content = f"🚨 {games_role.mention} {game.title()} has been refreshed!")