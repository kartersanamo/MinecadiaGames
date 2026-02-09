import random
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict
import discord
from games.base.dm_game import DMGame
from managers.leveling import LevelingManager
from utils.helpers import get_last_game_id
from core.database.pool import DatabasePool
from core.logging.setup import get_logger


class Memory(DMGame):
    def __init__(self, bot):
        super().__init__(bot)
        # Support both old and new config structure
        games = self.dm_config.get('GAMES', {})
        if not games:
            games = self.dm_config.get('games', {})
        self.game_config = games.get('Memory', {})
        self.logger = get_logger("DMGames")
    
    async def _run_game(self, user: discord.User, game_name: str, test_mode: bool = False) -> bool:
        try:
            if test_mode:
                last_game_id = -999999  # Fake game_id for test mode
            else:
                last_game_id = await get_last_game_id('memory')
                if not last_game_id:
                    return False
            
            # Support both old and new structure
            tries = self.game_config.get('TRIES') or self.game_config.get('max_tries', 7)
            image_url = self.game_config.get('IMAGE') or self.game_config.get('image_url')
            
            test_label = " 🧪 TEST GAME 🧪" if test_mode else ""
            
            embed = discord.Embed(
                title=f"Memory #{last_game_id}{test_label}",
                description="Welcome to Memory! Begin by clicking on any two buttons below to try to match!",
                color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR'))
            )
            embed.add_field(name="Tries Remaining", value=str(tries))
            embed.add_field(name="Matches Found", value="0/10", inline=True)
            if image_url:
                embed.set_image(url=image_url)
            from utils.helpers import get_embed_logo_url
            logo_url = get_embed_logo_url(self.config.get('config', 'LOGO'))
            embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
            
            view = MemoryButtons(last_game_id, self.bot, self.config, self.game_config, self.dm_config, test_mode=test_mode)
            view.player_id = user.id  # Store player_id for state saving
            # Register view for persistence across bot restarts
            self.bot.add_view(view)
            await user.send(embed=embed, view=view)
            
            # Save initial state
            if not test_mode:
                await view._save_state()
            
            if not test_mode:
                db = await self._get_db()
                current_unix = int(datetime.now(timezone.utc).timestamp())
                await db.execute_insert(
                    "INSERT INTO users_memory (game_id, user_id, won, attempts, matches, started_at, ended_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (last_game_id, user.id, 'Started', 0, 0, current_unix, 0)
                )
            
            self.logger.info(f"Memory ({user.name}#{user.discriminator}){' [TEST MODE]' if test_mode else ''}")
            return True
        except Exception as e:
            self.logger.error(f"Memory error: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            return False


class MemoryButtons(discord.ui.View):
    def __init__(self, game_id: int, bot, config, game_config, dm_config, test_mode: bool = False, saved_state: dict = None):
        super().__init__(timeout=None)
        self.game_id = game_id
        self.bot = bot
        self.config = config
        self.game_config = game_config
        self.dm_config = dm_config
        self.test_mode = test_mode
        
        self.button_cooldown = self.dm_config.get('BUTTON_COOLDOWN', 0.8) or self.dm_config.get('button_cooldown', 0.8)
        self.cooldowns: Dict[int, datetime] = {}
        self.is_processing = False  # Lock to prevent concurrent clicks
        self.total_xp = 0
        
        # Initialize or restore game state
        if saved_state:
            self._restore_state(saved_state)
        else:
            # Support both old (EMOJIS) and new (emojis) structure
            memory_emojis = self.game_config.get('EMOJIS', []) or self.game_config.get('emojis', [])
            if not memory_emojis:
                # Default emojis if none provided
                memory_emojis = ["🧠", "🎮", "🎯", "🎲", "🎪", "🎨", "🎭", "🎬", "🎤", "🎧"]
            
            # Create pairs and shuffle
            memory_emojis = memory_emojis[:10]  # Limit to 10 pairs (20 cards)
            self.card_values = (memory_emojis * 2)
            random.shuffle(self.card_values)
            
            # Game state
            self.tries_remaining = self.game_config.get('TRIES') or self.game_config.get('max_tries', 7)
            self.matches_found = 0
            self.selected_cards: List[int] = []  # Store indices of currently selected cards
            self.matched_cards: set = set()  # Store indices of matched cards
            self.game_ended = False
        
        # Create 20 buttons (4 rows x 5 columns)
        for i in range(20):
            row = i // 5
            button = discord.ui.Button(
                emoji="❓",
                style=discord.ButtonStyle.grey,
                custom_id=f"mem_{i}_{game_id}",
                row=row
            )
            button.callback = self.create_callback(i)
            self.add_item(button)
    
    def _get_state(self) -> dict:
        """Get current game state as dictionary"""
        return {
            'card_values': self.card_values[:],  # Copy list
            'selected_cards': self.selected_cards[:],  # Copy list
            'matched_cards': list(self.matched_cards),  # Convert set to list
            'tries_remaining': self.tries_remaining,
            'matches_found': self.matches_found,
            'game_ended': self.game_ended
        }
    
    def _restore_state(self, state: dict):
        """Restore game state from dictionary"""
        self.card_values = state.get('card_values', [])
        self.selected_cards = state.get('selected_cards', [])
        self.matched_cards = set(state.get('matched_cards', []))
        self.tries_remaining = state.get('tries_remaining', 7)
        self.matches_found = state.get('matches_found', 0)
        self.game_ended = state.get('game_ended', False)
        
        # Update button states to match (use _card_value_to_emoji so custom emojis render)
        for i in range(20):
            button = self._get_button(i)
            if button:
                if i in self.matched_cards:
                    button.emoji = self._card_value_to_emoji(self.card_values[i])
                    button.style = discord.ButtonStyle.green
                    button.disabled = True
                elif i in self.selected_cards:
                    button.emoji = self._card_value_to_emoji(self.card_values[i])
                    button.style = discord.ButtonStyle.blurple
                elif self.game_ended:
                    button.disabled = True
    
    async def _save_state(self):
        """Save current game state to database"""
        if self.test_mode or self.game_id == -999999 or not hasattr(self, 'player_id'):
            return
        
        try:
            from utils.game_state_manager import save_game_state
            state = self._get_state()
            await save_game_state('memory', self.game_id, self.player_id, state, self.test_mode)
        except Exception as e:
            from core.logging.setup import get_logger
            logger = get_logger("DMGames")
            logger.error(f"Error saving Memory game state: {e}")
    
    def create_callback(self, index: int):
        async def callback(interaction: discord.Interaction):
            await self.handle_click(interaction, index)
        return callback
    
    async def handle_click(self, interaction: discord.Interaction, index: int):
        user_id = interaction.user.id
        
        # Check if game is still valid
        if not await self._check_valid_game(interaction):
            return
        
        # Check if game has ended
        if self.game_ended:
            await interaction.response.send_message("`❌` This game has already ended!", ephemeral=True)
            return
        
        # Check cooldown
        if user_id in self.cooldowns and datetime.now(timezone.utc) < self.cooldowns[user_id]:
            remaining = (self.cooldowns[user_id] - datetime.now(timezone.utc)).total_seconds()
            await interaction.response.send_message(
                f"`❌` You need to wait {remaining:.2f} seconds before using this button again.",
                ephemeral=True
            )
            return
        
        # Prevent concurrent processing
        if self.is_processing:
            await interaction.response.send_message("`⏳` Please wait for the current action to complete.", ephemeral=True)
            return
        
        # Get the button
        button = self._get_button(index)
        if not button:
            await interaction.response.send_message("`❌` Button not found!", ephemeral=True)
            return
        
        # Check if card is already matched
        if index in self.matched_cards:
            await interaction.response.send_message("`❌` This card is already matched!", ephemeral=True)
            return
        
        # Check if card is already selected
        if index in self.selected_cards:
            await interaction.response.send_message("`❌` This card is already selected!", ephemeral=True)
            return
        
        # Check if we already have 2 cards selected (waiting for them to be processed)
        if len(self.selected_cards) >= 2:
            await interaction.response.send_message("`⏳` Please wait for the current pair to be processed.", ephemeral=True)
            return
        
        # Defer response
        await interaction.response.defer()
        
        # Set processing lock
        self.is_processing = True
        
        try:
            # Reveal the card (use _card_value_to_emoji so custom emojis like :clown: render instead of staying blue)
            self.selected_cards.append(index)
            self._sync_buttons_from_state()
            
            # Update the view
            await interaction.message.edit(view=self)
            
            # If we have 2 cards selected, check for match
            if len(self.selected_cards) == 2:
                await self._check_match(interaction)
            else:
                # Save state after card selection (before match check)
                await self._save_state()
            
            # Set cooldown
            self.cooldowns[user_id] = datetime.now(timezone.utc) + timedelta(seconds=self.button_cooldown)
        finally:
            self.is_processing = False
    
    async def _check_match(self, interaction: discord.Interaction):
        """Check if the two selected cards match."""
        if len(self.selected_cards) != 2:
            return
        
        index1, index2 = self.selected_cards
        card1_value = self.card_values[index1]
        card2_value = self.card_values[index2]
        
        button1 = self._get_button(index1)
        button2 = self._get_button(index2)
        
        if not button1 or not button2:
            return
        
        embed = interaction.message.embeds[0]
        
        # Check if cards match
        if card1_value == card2_value:
            # Match found!
            self.matches_found += 1
            self.matched_cards.add(index1)
            self.matched_cards.add(index2)
            
            # Award XP for match
            match_xp = self.game_config.get('MATCH_XP', {}) or self.game_config.get('xp', {}).get('match', {})
            xp = random.randint(
                match_xp.get('LOWER') or match_xp.get('min', 10),
                match_xp.get('UPPER') or match_xp.get('max', 20)
            )
            self.total_xp += xp
            
            # Update database
            db = await DatabasePool.get_instance()
            await db.execute(
                "UPDATE users_memory SET matches = matches + 1 WHERE user_id = %s AND game_id = %s",
                (interaction.user.id, self.game_id)
            )
            
            # Update embed
            embed.set_field_at(1, name="Matches Found", value=f"{self.matches_found}/10", inline=True)
            
            # Check if game is won
            if self.matches_found >= 10:
                await self._handle_win(interaction, embed)
                return
            
            # Clear selected cards
            self.selected_cards.clear()
            
            # Save state after match
            await self._save_state()
            
            # Sync button styles from state so matched tiles always show green (fixes visual glitch)
            self._sync_buttons_from_state()
            await interaction.message.edit(embed=embed, view=self)
        else:
            # No match - flip cards back
            self.tries_remaining -= 1
            
            # Update database
            db = await DatabasePool.get_instance()
            await db.execute(
                "UPDATE users_memory SET attempts = attempts + 1 WHERE user_id = %s AND game_id = %s",
                (interaction.user.id, self.game_id)
            )
            
            # Update embed
            embed.set_field_at(0, name="Tries Remaining", value=str(self.tries_remaining))
            
            # Show cards briefly (red = no match), then flip back
            self._sync_buttons_from_state()
            for idx in (index1, index2):
                b = self._get_button(idx)
                if b:
                    b.style = discord.ButtonStyle.red
            await interaction.message.edit(embed=embed, view=self)
            
            # Wait 1.5 seconds before flipping back
            await asyncio.sleep(1.5)
            
            # Check if game is lost
            if self.tries_remaining <= 0:
                await self._handle_loss(interaction, embed)
                return
            
            # Flip cards back
            self.selected_cards.clear()
            self._sync_buttons_from_state()
            
            # Save state after match
            await self._save_state()
            
            # Update message
            await interaction.message.edit(embed=embed, view=self)
    
    async def _handle_win(self, interaction: discord.Interaction, embed: discord.Embed):
        """Handle game win."""
        self.game_ended = True
        
        # Save final state
        await self._save_state()
        
        # Award win XP
        win_xp = self.game_config.get('WIN_XP', {}) or self.game_config.get('xp', {}).get('win', {})
        xp = random.randint(
            win_xp.get('LOWER') or win_xp.get('min', 60),
            win_xp.get('UPPER') or win_xp.get('max', 70)
        )
        self.total_xp += xp
        
        # Sync all button styles from state (matched = green), then disable all
        self._sync_buttons_from_state()
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        
        # Update embed
        if self.test_mode:
            embed.description = f"🎉 **Game Complete!** You found all matches!\n\nTotal XP Would Have Been: `{self.total_xp}xp`"
        else:
            embed.description = f"🎉 **Game Complete!** You found all matches!\n\nTotal XP Earned: `{self.total_xp}xp`"
        embed.set_field_at(0, name="Tries Remaining", value="0")
        embed.set_field_at(1, name="Matches Found", value="10/10", inline=True)
        
        # Update message
        await interaction.message.edit(embed=embed, view=self)
        
        if self.test_mode:
            # Send win message for test mode
            await interaction.channel.send(
                f"`✅` Congratulations {interaction.user.mention}! You won! You would have earned `{self.total_xp}xp`!"
            )
        else:
            # Award XP
            lvl_mng = LevelingManager(
                user=interaction.user,
                channel=interaction.channel,
                client=self.bot,
                xp=self.total_xp,
                source="Memory",
                game_id=self.game_id
            )
            await lvl_mng.update()
            
            # Send win message
            await interaction.channel.send(
                f"`✅` Congratulations {interaction.user.mention}! You won `{self.total_xp}xp`!"
            )
            
            # Update database
            db = await DatabasePool.get_instance()
            current_unix = int(datetime.now(timezone.utc).timestamp())
            await db.execute(
                "UPDATE users_memory SET won = 'Won', ended_at = %s WHERE user_id = %s AND game_id = %s",
                (current_unix, interaction.user.id, self.game_id)
            )
            
            # Check for achievements
            from utils.achievements import check_dm_game_win
            await check_dm_game_win(interaction.user, "Memory", interaction.channel, self.bot)
    
    async def _handle_loss(self, interaction: discord.Interaction, embed: discord.Embed):
        """Handle game loss."""
        self.game_ended = True
        
        # Save final state
        await self._save_state()
        
        # Sync button styles (matched = green) then disable all
        self._sync_buttons_from_state()
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        
        # Update embed
        if self.test_mode:
            embed.description = f"❌ **Game Over!** You ran out of tries.\n\nTotal XP Would Have Been: `{self.total_xp}xp`"
        else:
            embed.description = f"❌ **Game Over!** You ran out of tries.\n\nTotal XP Earned: `{self.total_xp}xp`"
        embed.set_field_at(0, name="Tries Remaining", value="0")
        
        # Update message
        await interaction.message.edit(embed=embed, view=self)
        
        if self.total_xp > 0:
            if self.test_mode:
                await interaction.channel.send(
                    f"`❌` Sorry {interaction.user.mention}! You ran out of tries. You would have earned `{self.total_xp}xp`."
                )
            else:
                lvl_mng = LevelingManager(
                    user=interaction.user,
                    channel=interaction.channel,
                    client=self.bot,
                    xp=self.total_xp,
                    source="Memory",
                    game_id=self.game_id
                )
                await lvl_mng.update()
                
                await interaction.channel.send(
                    f"`❌` Sorry {interaction.user.mention}! You ran out of tries. You earned `{self.total_xp}xp`."
                )
        else:
            await interaction.channel.send(
                f"`❌` Sorry {interaction.user.mention}! You ran out of tries."
            )
        
        # Update database
        if not self.test_mode:
            db = await DatabasePool.get_instance()
            current_unix = int(datetime.now(timezone.utc).timestamp())
            await db.execute(
                "UPDATE users_memory SET won = 'Lost', ended_at = %s WHERE user_id = %s AND game_id = %s",
                (current_unix, interaction.user.id, self.game_id)
            )
    
    @staticmethod
    def _card_value_to_emoji(card_value: str):
        """Convert card value to a form Discord buttons can display.
        Custom emojis must be discord.PartialEmoji; raw '<:name:id>' strings don't render (button stays blue).
        """
        if not card_value or not isinstance(card_value, str):
            return "❓"
        # Unicode emoji: use as-is (no leading < or :)
        if not card_value.startswith("<") or not card_value.endswith(">"):
            return card_value
        # Custom emoji: <:name:id> or <a:name:id>
        try:
            is_animated = card_value.startswith("<a:")
            inner = card_value[1:-1]
            if is_animated:
                inner = inner[2:]  # strip 'a:'
            else:
                inner = inner[1:]   # strip ':'
            parts = inner.split(":", 1)
            if len(parts) == 2:
                name, emoji_id = parts
                return discord.PartialEmoji(name=name, id=int(emoji_id), animated=is_animated)
        except (ValueError, TypeError):
            pass
        return card_value  # fallback

    def _get_button(self, index: int) -> Optional[discord.ui.Button]:
        """Get button by index."""
        for child in self.children:
            if isinstance(child, discord.ui.Button) and child.custom_id == f"mem_{index}_{self.game_id}":
                return child
        return None

    def _sync_buttons_from_state(self):
        """Sync all button styles/emoji/disabled from game state. Call before every message.edit(view=self)
        so matched tiles always render green and we avoid visual glitches where they stay blue.
        """
        for i in range(20):
            button = self._get_button(i)
            if not button:
                continue
            if i in self.matched_cards:
                button.style = discord.ButtonStyle.green
                button.disabled = True
                button.emoji = self._card_value_to_emoji(self.card_values[i])
            elif i in self.selected_cards:
                button.style = discord.ButtonStyle.blurple
                button.emoji = self._card_value_to_emoji(self.card_values[i])
                button.disabled = False
            else:
                button.style = discord.ButtonStyle.grey
                button.emoji = "❓"
                button.disabled = self.game_ended
    
    async def _check_valid_game(self, interaction: discord.Interaction) -> bool:
        """Check if the game is still valid."""
        # Skip validation for test games
        if self.test_mode:
            return True
        
        last_game_id = await get_last_game_id('memory')
        if self.game_id != last_game_id:
            await interaction.response.send_message(
                "`❌` Sorry, but this game has already ended. Please go to the leveling channel to begin another one!",
                ephemeral=True
            )
            return False
        return True
