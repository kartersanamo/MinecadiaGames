import asyncio
from datetime import datetime, timedelta, timezone

import discord

from core.database.pool import DatabasePool
from core.logging.setup import get_logger
from games.dm.filler.filler_engine import (
    DEFAULT_COLORS,
    FillerState,
    OWNER_BOT,
    OWNER_PLAYER,
    calculate_xp,
)
from managers.leveling import LevelingManager


class FillerButtons(discord.ui.View):
    def __init__(
        self,
        game_id: int,
        bot,
        config,
        game_config,
        test_mode: bool = False,
        saved_state: dict = None,
    ):
        super().__init__(timeout=None)
        self.game_id = game_id
        self.bot = bot
        self.config = config
        self.game_config = game_config
        self.test_mode = test_mode
        self.dm_config = config.get("dm_games") or {}
        self.button_cooldown = float(
            game_config.get("button_cooldown")
            or self.dm_config.get("button_cooldown")
            or self.dm_config.get("BUTTON_COOLDOWN", 0.8)
        )
        self.turn_delay = float(game_config.get("turn_delay_ms", 1200)) / 1000.0
        self.bot_delay = float(game_config.get("bot_delay_ms", 800)) / 1000.0
        self.colors = game_config.get("colors") or DEFAULT_COLORS
        self.cooldowns = {}
        self._move_lock = asyncio.Lock()
        self.logger = get_logger("DMGames")
        self.player_id = None
        self.message = None

        grid_size = int(game_config.get("grid_size", 6))
        if saved_state:
            self.state = FillerState.from_dict(saved_state, colors=self.colors)
            if not self.state.game_ended and not self.state.is_player_turn:
                self.state.is_player_turn = True
        else:
            self.state = FillerState(grid_size=grid_size, colors=self.colors)

        xp_cfg = game_config.get("xp") or game_config.get("WIN_XP") or {}
        self.win_min = int(xp_cfg.get("win_min") or xp_cfg.get("LOWER", 40))
        self.win_max = int(xp_cfg.get("win_max") or xp_cfg.get("UPPER", 70))

        for color_idx in range(len(self.colors)):
            button = discord.ui.Button(
                label=self.colors[color_idx],
                style=discord.ButtonStyle.secondary,
                custom_id=f"filler_{color_idx}_{game_id}",
                row=color_idx // 3,
            )
            button.callback = self._make_callback(color_idx)
            self.add_item(button)

        self._sync_button_states()

    def _make_callback(self, color_idx: int):
        async def callback(interaction: discord.Interaction):
            await self.handle_color_pick(interaction, color_idx)

        return callback

    def _get_state(self) -> dict:
        data = self.state.to_dict()
        data["game_ended"] = self.state.game_ended
        return data

    def _restore_state(self, state: dict):
        self.state = FillerState.from_dict(state, colors=self.colors)

    async def _save_state(self):
        if self.test_mode or self.game_id == -999999 or not self.player_id:
            return
        try:
            await self.bot.app.game_state.save(
                "filler", self.game_id, self.player_id, self._get_state(), self.test_mode
            )
        except Exception as e:
            self.logger.error(f"Error saving Filler game state: {e}")

    def _sync_button_states(self):
        if self.state.game_ended or not self.state.is_player_turn:
            for child in self.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = True
                    child.style = discord.ButtonStyle.danger
            return

        legal = set(self.state.legal_moves(OWNER_PLAYER))
        for child in self.children:
            if not isinstance(child, discord.ui.Button):
                continue
            parts = child.custom_id.split("_")
            if len(parts) < 2:
                child.disabled = True
                child.style = discord.ButtonStyle.danger
                continue
            color_idx = int(parts[1])
            is_legal = color_idx in legal
            child.disabled = not is_legal
            child.style = (
                discord.ButtonStyle.secondary if is_legal else discord.ButtonStyle.danger
            )

    def build_embed(self, title_suffix: str = "") -> discord.Embed:
        test_label = " 🧪 TEST GAME 🧪" if self.test_mode else ""
        embed = discord.Embed(
            title=f"Filler #{self.game_id}{test_label}{title_suffix}",
            description=self.state.render_grid(),
            color=discord.Color.from_str(self.config.get("config", "EMBED_COLOR")),
        )
        embed.add_field(name="You", value=f"{self.state.player_cells} cells", inline=True)
        embed.add_field(name="Bot", value=f"{self.state.bot_cells} cells", inline=True)
        embed.add_field(
            name="Your color",
            value=self.colors[self.state.player_color],
            inline=False
        )
        embed.add_field(
            name="Bot color",
            value=self.colors[self.state.bot_color],
            inline=True
        )
        if self.state.game_ended:
            turn_text = "Game over"
        elif self.state.is_player_turn:
            turn_text = "Your move — pick a color below"
        else:
            turn_text = "Bot is thinking..."
        embed.add_field(name="Turn", value=turn_text, inline=False)
        logo_url = self.bot.app.embeds.get_logo_url(self.config.get("config", "LOGO"))
        embed.set_footer(text=self.config.get("config", "FOOTER"), icon_url=logo_url)
        return embed

    async def _refresh_message(self, interaction: discord.Interaction):
        """Update embed + button states on the game message."""
        self._sync_button_states()
        embed = self.build_embed()
        target = self.message or interaction.message
        if target:
            try:
                await target.edit(embed=embed, view=self)
            except discord.NotFound:
                pass
            except Exception as e:
                self.logger.error(f"Error refreshing Filler message: {e}")

    async def _run_bot_turn(self, interaction: discord.Interaction):
        """Apply exactly one bot move, then return control to the player."""
        bot_move = self.state.bot_move(OWNER_BOT)
        if bot_move is not None:
            self.state.apply_move(OWNER_BOT, bot_move)
            await asyncio.sleep(self.bot_delay)

    async def _check_valid_game(self, interaction: discord.Interaction) -> bool:
        if self.test_mode:
            return True
        last_game_id = await self.bot.app.games.get_last_game_id("filler")
        if self.game_id != last_game_id:
            await interaction.response.send_message(
                "`❌` Sorry, but this game has already ended. Please go to the leveling channel to begin another one!",
                ephemeral=True,
            )
            return False
        return True

    async def handle_color_pick(self, interaction: discord.Interaction, color_idx: int):
        if not await self._check_valid_game(interaction):
            return

        if self.state.game_ended:
            await interaction.response.send_message(
                "`❌` This game has already ended.",
                ephemeral=True,
            )
            return

        if not self.state.is_player_turn:
            await interaction.response.send_message(
                "`❌` Wait for the bot to finish its turn.",
                ephemeral=True,
            )
            return

        user_id = interaction.user.id
        if user_id in self.cooldowns and datetime.now(timezone.utc) < self.cooldowns[user_id]:
            remaining = (self.cooldowns[user_id] - datetime.now(timezone.utc)).total_seconds()
            await interaction.response.send_message(
                f"❌ You need to wait {remaining:.2f} seconds before using this button again.",
                ephemeral=True,
            )
            return

        legal = self.state.legal_moves(OWNER_PLAYER)
        if color_idx not in legal:
            await interaction.response.send_message(
                "`❌` That color is not a valid move.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        async with self._move_lock:
            if self.state.game_ended or not self.state.is_player_turn:
                return

            self.cooldowns[user_id] = datetime.now(timezone.utc) + timedelta(
                seconds=self.button_cooldown
            )

            try:
                self.state.apply_move(OWNER_PLAYER, color_idx)

                if self.state.check_game_over():
                    await self._refresh_message(interaction)
                    await self._finish_game(interaction)
                    return

                self.state.is_player_turn = False
                await self._refresh_message(interaction)
                await asyncio.sleep(self.turn_delay)

                await self._run_bot_turn(interaction)

                if self.state.check_game_over():
                    await self._refresh_message(interaction)
                    await self._finish_game(interaction)
                    return

                self.state.is_player_turn = True
                await self._refresh_message(interaction)
                await self._save_state()
            except Exception as e:
                self.logger.error(f"Error during Filler turn: {e}")
                import traceback

                self.logger.error(traceback.format_exc())
                if not self.state.game_ended:
                    self.state.is_player_turn = True
                    await self._refresh_message(interaction)
                try:
                    await interaction.followup.send(
                        "`❌` Something went wrong on that turn. It's your move again — please pick a color.",
                        ephemeral=True,
                    )
                except Exception:
                    pass

    async def _finish_game(self, interaction: discord.Interaction):
        self.state.game_ended = True
        self.state.is_player_turn = False
        self._sync_button_states()

        winner = self.state.winner()
        total = self.state.grid_size * self.state.grid_size
        current_unix = int(datetime.now(timezone.utc).timestamp())
        db = await DatabasePool.get_instance()

        if winner == OWNER_PLAYER:
            xp = calculate_xp(self.state.player_cells, total, self.win_min, self.win_max)
            result_msg = (
                f"`✅` You won with **{self.state.player_cells}** cells "
                f"(bot had **{self.state.bot_cells}**)! "
            )
            if self.test_mode:
                result_msg += f"You would have earned `{xp}xp`!"
            else:
                result_msg += f"You earned `{xp}xp`!"
                lvl_mng = LevelingManager(
                    user=interaction.user,
                    channel=interaction.channel,
                    client=self.bot,
                    xp=xp,
                    source="Filler",
                    game_id=self.game_id,
                )
                await lvl_mng.update()
                await self.bot.app.achievements.check_dm_game_win(
                    interaction.user, "Filler", interaction.channel, self.bot
                )
                await db.execute(
                    "UPDATE users_filler SET won = 'Won', player_cells = %s, bot_cells = %s, "
                    "turns = %s, ended_at = %s WHERE user_id = %s AND game_id = %s",
                    (
                        self.state.player_cells,
                        self.state.bot_cells,
                        self.state.turns,
                        current_unix,
                        interaction.user.id,
                        self.game_id,
                    ),
                )
        elif winner == OWNER_BOT:
            result_msg = (
                f"`❌` You lost! The bot had **{self.state.bot_cells}** cells "
                f"and you had **{self.state.player_cells}**."
            )
            if not self.test_mode:
                await db.execute(
                    "UPDATE users_filler SET won = 'Lost', player_cells = %s, bot_cells = %s, "
                    "turns = %s, ended_at = %s WHERE user_id = %s AND game_id = %s",
                    (
                        self.state.player_cells,
                        self.state.bot_cells,
                        self.state.turns,
                        current_unix,
                        interaction.user.id,
                        self.game_id,
                    ),
                )
        else:
            win_xp = calculate_xp(self.state.player_cells, total, self.win_min, self.win_max)
            xp = max(1, round(win_xp / 2))
            result_msg = (
                f"`🤝` It's a tie! Both sides had **{self.state.player_cells}** cells. "
            )
            if self.test_mode:
                result_msg += f"You would have earned `{xp}xp` (half of a win)!"
            else:
                result_msg += f"You earned `{xp}xp` (half of a win)!"
                lvl_mng = LevelingManager(
                    user=interaction.user,
                    channel=interaction.channel,
                    client=self.bot,
                    xp=xp,
                    source="Filler",
                    game_id=self.game_id,
                )
                await lvl_mng.update()
                await db.execute(
                    "UPDATE users_filler SET won = 'Tied', player_cells = %s, bot_cells = %s, "
                    "turns = %s, ended_at = %s WHERE user_id = %s AND game_id = %s",
                    (
                        self.state.player_cells,
                        self.state.bot_cells,
                        self.state.turns,
                        current_unix,
                        interaction.user.id,
                        self.game_id,
                    ),
                )

        embed = self.build_embed()
        embed.add_field(name="Result", value=result_msg, inline=False)
        try:
            await interaction.message.edit(embed=embed, view=self)
        except discord.NotFound:
            pass

        try:
            await interaction.channel.send(result_msg)
        except Exception:
            pass

        await self._save_state()
