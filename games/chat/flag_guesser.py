import asyncio
import random
import os
import uuid
import urllib.request
import json
import requests
from datetime import datetime, timezone
from typing import Optional, List, Tuple
import discord
from games.base.chat_game import ChatGame
from managers.leveling import LevelingManager
from core.logging.setup import get_logger


class FlagGuesser(ChatGame):
    def __init__(self, bot):
        super().__init__(bot)
        # Support both old and new config structure
        games = self.chat_config.get('GAMES', {})
        if not games:
            flag_config = self.config.get('flag_guesser', {})
            self.game_config = {
                'API_URL': flag_config.get('api', {}).get('url'),
                'REQUEST_HEADERS': flag_config.get('api', {}).get('headers', {})
            }
        else:
            self.game_config = games.get('Flag Guesser', {})
        self.countries = self._fetch_countries()
        self.logger = get_logger("ChatGames")
    
    def _fetch_countries(self) -> dict:
        api_url = self.game_config.get('API_URL', 'https://flagcdn.com/en/codes.json')
        headers = self.game_config.get('REQUEST_HEADERS', {})
        
        request = urllib.request.Request(url=api_url, headers=headers)
        with urllib.request.urlopen(request) as response:
            countries = json.loads(response.read())
        
        return {k: v for k, v in countries.items() if not k.startswith('us-')}
    
    async def _select_country_and_answers(self) -> Tuple[str, str, List[str]]:
        country_code = random.choice(list(self.countries.keys()))
        correct_answer = self.countries[country_code]
        answers = [correct_answer]
        
        while len(answers) < 4:
            choice = random.choice(list(self.countries.values()))
            if choice not in answers:
                answers.append(choice)
        
        random.shuffle(answers)
        return country_code, correct_answer, answers
    
    async def _build_embed(self, country_code: str, xp_multiplier: float, end_time: int, test_mode: bool = False) -> Tuple[discord.Embed, discord.File]:
        response = requests.get(f"https://flagcdn.com/w2560/{country_code}.png")
        filename = f"{uuid.uuid4()}.png"
        
        with open(filename, 'wb') as f:
            f.write(response.content)
        
        # Build title with XP multiplier and test mode
        xp_title = ""
        if xp_multiplier == 2.0:
            xp_title = " (DOUBLE XP)"
        elif xp_multiplier == 3.0:
            xp_title = " (TRIPLE XP)"
        elif xp_multiplier > 1.0:
            xp_title = f" ({xp_multiplier:.1f}x XP)"
        
        test_label = " 🧪 TEST GAME 🧪" if test_mode else ""
        
        embed = discord.Embed(
            title=f"Flag Guesser{test_label}{xp_title}",
            description=f"This game will end <t:{end_time}:R>",
            color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR')),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_image(url=f"attachment://{filename}")
        
        file = discord.File(filename, filename=filename)
        return embed, file
    
    async def _run_game(self, channel: discord.TextChannel, xp_multiplier: float = 1.0, test_mode: bool = False) -> Optional[discord.Message]:
        try:
            game_length = self.chat_config.get('GAME_LENGTH') or self.chat_config.get('game_duration', 600)
            current_unix = int(datetime.now(timezone.utc).timestamp())
            end_time = current_unix + game_length
            
            game_id = await self._create_game_entry('Flag Guesser', False, test_mode=test_mode, end_time=end_time)
            
            guild = self.bot.get_guild(self.config.get('config', 'GUILD_ID'))
            if not guild:
                self.logger.error("Error fetching guild")
                return None
            
            role = guild.get_role(self.config.get('config', 'GAMES_ROLE'))
            if not role:
                self.logger.error("Games role not found")
                return None
            
            # Use custom XP multiplier if provided, otherwise random 15% chance for 2x
            if xp_multiplier > 1.0:
                xp_mult = xp_multiplier
            else:
                double_xp = random.random() <= 0.15
                xp_mult = 2.0 if double_xp else 1.0
            
            country_code, correct_answer, answers = await self._select_country_and_answers()
            
            self.logger.info(f"Flag Guesser '{correct_answer}' #{channel.name}")
            
            view = CountryButtons(correct_answer, answers, xp_mult, game_id, self.bot, self.config, test_mode=test_mode)
            embed, file = await self._build_embed(country_code, xp_mult, end_time, test_mode=test_mode)
            from utils.helpers import get_embed_logo_url
            logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
            embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
            
            # Store the file object and path for later edits (need to re-attach on every edit)
            view.current_image_file = file
            view.current_image_path = file.filename  # Store path to recreate file object
            
            # Register view for persistence across bot restarts
            self.bot.add_view(view)
            message = await channel.send(
                content=role.mention,
                embed=embed,
                view=view,
                file =file
            )
            view.message = message  # Store message reference for real-time updates
            
            # Register game in registry for admin commands
            from utils.chat_game_registry import registry
            original_state = {
                'correct_answer': correct_answer,
                'country_code': country_code,
                'answers': answers,
                'embed': {
                    'title': embed.title,
                    'description': embed.description,
                    'fields': [{'name': f.name, 'value': f.value, 'inline': f.inline} for f in embed.fields]
                }
            }
            registry.register_game(
                message.id,
                'flag_guesser',
                game_id,
                view,
                original_state,
                xp_mult,
                test_mode
            )
            game_data = registry.get_game(message.id)
            if game_data:
                game_data['image_file'] = file
            
            # Store message and end_time for timer task
            view.message = message
            view.end_time = end_time
            view.game_id = game_id
            
            # Start timer task that will end the game
            asyncio.create_task(self._game_timer(message, view, end_time, game_id, file))
            
            return message
        except Exception as e:
            self.logger.error(f"Flag Guesser error: {e}")
            return None
    
    async def _game_timer(self, message: discord.Message, view, end_time: int, game_id: int, file: discord.File):
        """Timer task that ends the game at the specified time"""
        try:
            current_time = int(datetime.now(timezone.utc).timestamp())
            remaining_time = end_time - current_time
            
            if remaining_time > 0:
                await asyncio.sleep(remaining_time)
            
            # Check if game is still active
            try:
                if message.components:
                    embed = message.embeds[0] if message.embeds else discord.Embed()
                    embed.description = f"This game ended <t:{end_time}:R>"
                    
                    # Preserve the image by re-attaching the file
                    file_obj = None
                    if hasattr(view, 'current_image_path') and view.current_image_path and os.path.exists(view.current_image_path):
                        try:
                            file_obj = discord.File(view.current_image_path, filename=os.path.basename(view.current_image_path))
                            embed.set_image(url=f"attachment://{file_obj.filename}")
                        except Exception as e:
                            # If file doesn't exist, try to preserve existing image URL
                            if message.embeds and message.embeds[0].image and message.embeds[0].image.url:
                                embed.set_image(url=message.embeds[0].image.url)
                    elif message.embeds and message.embeds[0].image and message.embeds[0].image.url:
                        # Fallback: preserve existing image URL
                        embed.set_image(url=message.embeds[0].image.url)
                    
                    await message.edit(
                        embed=embed,
                        attachments=[file_obj] if file_obj else [],
                        view=None
                    )
                    
                    # Update game status to Finished
                    await self._update_game_status('Finished')
                    
                    # Unregister game from registry
                    from utils.chat_game_registry import registry
                    registry.unregister_game(message.id)
                    
                    # Clean up the image file at the end
                    try:
                        if hasattr(view, 'current_image_path') and view.current_image_path and os.path.exists(view.current_image_path):
                            os.remove(view.current_image_path)
                    except Exception as e:
                        self.logger.error(f"Error removing flag guesser image file: {e}")
            except discord.NotFound:
                # Message was deleted, that's okay
                pass
            except Exception as e:
                self.logger.error(f"Error ending flag guesser game {game_id}: {e}")
        except asyncio.CancelledError:
            # Timer was cancelled (e.g., game ended manually)
            pass
        except Exception as e:
            self.logger.error(f"Error in flag guesser timer: {e}")


class CountryButtons(discord.ui.View):
    def __init__(self, correct_answer: str, answers: List[str], xp_multiplier: float, game_id: int, bot, config, test_mode: bool = False):
        super().__init__(timeout=None)
        self.correct_answer = correct_answer
        self.answers = answers
        self.xp_multiplier = xp_multiplier
        self.double_xp = xp_multiplier >= 2.0  # For display purposes
        self.game_id = game_id
        self.bot = bot
        self.config = config
        self.test_mode = test_mode
        self.winners: List[dict] = []
        self.message: Optional[discord.Message] = None  # Store message reference
        self.current_image_file: Optional[discord.File] = None  # Store file for re-attaching on edits
        self.current_image_path: Optional[str] = None  # Store file path to recreate file object
        # Support both old and new XP structure
        chat_config = config.get('chat_games', {})
        xp_config = chat_config.get('XP', {})
        if not xp_config:
            xp_section = chat_config.get('xp', {})
            xp_config = {
                'XP_ADD': xp_section.get('base', 10),
                'XP_LOWER': xp_section.get('positions', {})
            }
        self.xp_config = xp_config
        self.winner_count = 0
        
        for answer in answers:
            button = discord.ui.Button(
                label=answer,
                style=discord.ButtonStyle.grey,
                custom_id=f"flag_{answer}_{game_id}"
            )
            button.callback = self.create_callback(answer)
            self.add_item(button)
    
    def create_callback(self, answer: str):
        async def callback(interaction: discord.Interaction):
            # Log activity
            from utils.chat_game_registry import registry
            if self.message:
                registry.log_activity(
                    self.message.id,
                    interaction.user.id,
                    'click',
                    f'Clicked: {answer[:50]}',
                    True
                )
            
            try:
                if answer == self.correct_answer:
                    # Check if user already won - do this check first to prevent race conditions
                    if interaction.user.id in [w['user_id'] for w in self.winners]:
                        if self.message:
                            registry.log_activity(
                                self.message.id,
                                interaction.user.id,
                                'denied',
                                'Already won',
                                False
                            )
                        if not interaction.response.is_done():
                            await interaction.response.send_message("You've already won this game!", ephemeral=True)
                        else:
                            await interaction.followup.send("You've already won this game!", ephemeral=True)
                        return
                    
                    # Add user to winners IMMEDIATELY to prevent race conditions
                    # We'll calculate XP and add full details after, but this prevents duplicate processing
                    self.winner_count += 1
                    position = self.winner_count
                
                    # New XP system: random ranges based on position
                    if position == 1:
                        xp = random.randint(50, 60)
                    elif position == 2:
                        xp = random.randint(40, 50)
                    elif position == 3:
                        xp = random.randint(30, 40)
                    elif position == 4:
                        xp = random.randint(20, 30)
                    elif position == 5:
                        xp = random.randint(10, 20)
                    else:  # 6th place and beyond - must be less than previous winner
                        # Get previous winner's final XP (after multiplier)
                        previous_final_xp = self.winners[-1]['xp'] if self.winners else 20 * self.xp_multiplier
                        # Get base XP that would result in less final XP
                        # We need: (base_xp * multiplier) < previous_final_xp
                        # So: base_xp < previous_final_xp / multiplier
                        max_base_xp = max(1, int(previous_final_xp / self.xp_multiplier) - 1)
                        # Ensure minimum base XP results in at least 10 XP after multiplier
                        # Calculate minimum base XP needed: base_xp * multiplier >= 10, so base_xp >= 10 / multiplier
                        min_base_xp_required = max(1, int((10 / self.xp_multiplier) + 0.999))  # Round up
                        min_base_xp = max(min_base_xp_required, max_base_xp - 9)  # Keep range reasonable (up to 10 XP range)
                        # Ensure min_base_xp < max_base_xp for randint
                        if min_base_xp >= max_base_xp:
                            min_base_xp = max(1, max_base_xp - 1)
                        xp = random.randint(min_base_xp, max_base_xp) if min_base_xp < max_base_xp else min_base_xp
                
                    # Apply XP multiplier
                    xp = int(xp * self.xp_multiplier)
                    # Ensure minimum XP is 10 (safety check)
                    xp = max(10, xp)
                    
                    # Now add full winner details
                    self.winners.append({
                        'user': interaction.user.mention,
                        'user_id': interaction.user.id,
                        'xp': xp
                    })
                    
                    # Award XP
                    lvl_mng = LevelingManager(
                        user=interaction.user,
                        channel=interaction.channel,
                        client=self.bot,
                        xp=xp,
                        source="Flag Guesser",
                        game_id=self.game_id,
                        test_mode=self.test_mode
                    )
                    await lvl_mng.update()
                    
                    # Log correct answer
                    if self.message:
                        registry.log_activity(
                            self.message.id,
                            interaction.user.id,
                            'correct_answer',
                            f'Won {xp} XP (position {position})',
                            True
                        )
                    
                    # Build XP message
                    xp_msg = ""
                    if self.xp_multiplier == 2.0:
                        xp_msg = " (2x XP)"
                    elif self.xp_multiplier == 3.0:
                        xp_msg = " (3x XP)"
                    elif self.xp_multiplier > 1.0:
                        xp_msg = f" ({self.xp_multiplier:.1f}x XP)"
                    
                    test_prefix = "🧪 [TEST] " if self.test_mode else ""
                    xp_display = f"would have been awarded `{xp}xp`" if self.test_mode else f"have been awarded `{xp}xp`"
                    
                    if not interaction.response.is_done():
                        await interaction.response.send_message(
                            f"`✅` {test_prefix}Correct! You {xp_display}{xp_msg}!",
                            ephemeral=True
                        )
                    else:
                        await interaction.followup.send(
                            f"`✅` {test_prefix}Correct! You {xp_display}{xp_msg}!",
                            ephemeral=True
                        )
                
                    # Update embed with winners list immediately
                    if self.message:
                        try:
                            embed = self.message.embeds[0]
                            winners_text = "\n".join(f"`+{w['xp']}xp` {w['user']}" for w in self.winners)
                            
                            # Check if Winners field exists and update it, otherwise add it
                            found_winners_field = False
                            for i, field in enumerate(embed.fields):
                                if field.name == "Winners":
                                    embed.set_field_at(i, name="Winners", value=winners_text, inline=False)
                                    found_winners_field = True
                                    break
                            if not found_winners_field:
                                embed.add_field(name="Winners", value=winners_text, inline=False)
                            
                            # Preserve the image by re-attaching the file
                            file = None
                            if hasattr(self, 'current_image_path') and self.current_image_path and os.path.exists(self.current_image_path):
                                try:
                                    file = discord.File(self.current_image_path, filename=os.path.basename(self.current_image_path))
                                    embed.set_image(url=f"attachment://{file.filename}")
                                except Exception as e:
                                    # If file doesn't exist, try to preserve existing image URL
                                    if embed.image and embed.image.url:
                                        embed.set_image(url=embed.image.url)

                            await self.message.edit(
                                embed=embed,
                                attachments=[file] if file else []
                            )

                        except Exception as e:
                            # If updating fails, log but don't break the game
                            import traceback
                            from core.logging.setup import get_logger
                            logger = get_logger("ChatGames")
                            logger.error(f"Error updating winners in embed: {e}\n{traceback.format_exc()}")
                else:
                    # Log wrong answer
                    if self.message:
                        registry.log_activity(
                            self.message.id,
                            interaction.user.id,
                            'wrong_answer',
                            f'Selected: {answer[:50]}',
                            False
                        )
                    if not interaction.response.is_done():
                        await interaction.response.send_message("`❌` Incorrect answer!", ephemeral=True)
                    else:
                        await interaction.followup.send("`❌` Incorrect answer!", ephemeral=True)
            except Exception as e:
                # Log any errors that occur during processing
                import traceback
                from core.logging.setup import get_logger
                logger = get_logger("ChatGames")
                logger.error(f"Error in flag guesser callback: {e}\n{traceback.format_exc()}")
                
                # Log the error to activity log
                if self.message:
                    registry.log_activity(
                        self.message.id,
                        interaction.user.id,
                        'error',
                        f'Error processing click: {str(e)[:50]}',
                        False
                    )
                
                # Try to send error message to user
                try:
                    if not interaction.response.is_done():
                        await interaction.response.send_message("`❌` An error occurred. Please try again.", ephemeral=True)
                    else:
                        await interaction.followup.send("`❌` An error occurred. Please try again.", ephemeral=True)
                except:
                    pass
        
        return callback

