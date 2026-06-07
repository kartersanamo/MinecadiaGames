import asyncio
from datetime import datetime, timedelta, timezone

import discord

from core.logging.setup import get_logger
from games.dm.paintball.paintball_engine import (
    PHASE_ENDED,
    PHASE_REVEALING,
    PHASE_SELECTING,
    POSITION_NAMES,
    PaintballState,
    calculate_xp,
    format_lives,
)
from managers.leveling import LevelingManager
from repositories.game_session_repository import GameSessionRepository


class PaintballButtons(discord.ui.View):
    HIDE_LABELS = ["⬅️ Left", "⬇️ Center", "➡️ Right"]
    SHOOT_LABELS = ["🎯 Left", "🎯 Center", "🎯 Right"]

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
            or self.dm_config.get("BUTTON_COOLDOWN", 1.0)
        )
        self.reveal_delay = float(game_config.get("reveal_delay_ms", 1500)) / 1000.0
        self.cooldowns = {}
        self._move_lock = asyncio.Lock()
        self.logger = get_logger("DMGames")
        self.player_id = None
        self.message = None

        max_lives = int(game_config.get("lives", 3))
        if saved_state:
            self.state = PaintballState.from_dict(saved_state)
            if self.state.game_ended:
                self.state.phase = PHASE_ENDED
            elif self.state.phase == PHASE_REVEALING:
                self.state.phase = PHASE_SELECTING
                self.state.clear_selection()
        else:
            self.state = PaintballState(max_lives=max_lives, player_lives=max_lives, bot_lives=max_lives)

        xp_cfg = game_config.get("xp") or game_config.get("WIN_XP") or {}
        self.win_min = int(xp_cfg.get("win_min") or xp_cfg.get("LOWER", 40))
        self.win_max = int(xp_cfg.get("win_max") or xp_cfg.get("UPPER", 60))

        for i in range(3):
            button = discord.ui.Button(
                label=self.HIDE_LABELS[i],
                style=discord.ButtonStyle.secondary,
                custom_id=f"pb_hide_{i}_{game_id}",
                row=0,
            )
            button.callback = self._make_hide_callback(i)
            self.add_item(button)

        for i in range(3):
            button = discord.ui.Button(
                label=self.SHOOT_LABELS[i],
                style=discord.ButtonStyle.secondary,
                custom_id=f"pb_shoot_{i}_{game_id}",
                row=1,
            )
            button.callback = self._make_shoot_callback(i)
            self.add_item(button)

        fire_button = discord.ui.Button(
            label="🔥 Fire!",
            style=discord.ButtonStyle.danger,
            custom_id=f"pb_fire_{game_id}",
            row=2,
        )
        fire_button.callback = self._fire_callback
        self.add_item(fire_button)

        self._sync_button_styles()

    def _make_hide_callback(self, index: int):
        async def callback(interaction: discord.Interaction):
            await self.handle_hide(interaction, index)

        return callback

    def _make_shoot_callback(self, index: int):
        async def callback(interaction: discord.Interaction):
            await self.handle_shoot(interaction, index)

        return callback

    async def _fire_callback(self, interaction: discord.Interaction):
        await self.handle_fire(interaction)

    def _get_state(self) -> dict:
        return self.state.to_dict()

    async def _save_state(self):
        if self.test_mode or self.game_id == -999999 or not self.player_id:
            return
        try:
            await self.bot.app.game_state.save(
                "paintball", self.game_id, self.player_id, self._get_state(), self.test_mode
            )
        except Exception as e:
            self.logger.error(f"Error saving Paintball game state: {e}")

    def _sync_button_styles(self):
        ended = self.state.game_ended or self.state.phase == PHASE_ENDED
        selecting = self.state.phase == PHASE_SELECTING and not ended

        for child in self.children:
            if not isinstance(child, discord.ui.Button):
                continue

            if child.custom_id == f"pb_fire_{self.game_id}":
                child.disabled = ended or not self.state.ready_to_fire()
                child.style = discord.ButtonStyle.danger
                continue

            if child.custom_id.startswith("pb_hide_"):
                idx = int(child.custom_id.split("_")[2])
                if ended:
                    child.disabled = True
                    child.style = discord.ButtonStyle.secondary
                elif not selecting:
                    child.disabled = True
                    child.style = discord.ButtonStyle.secondary
                else:
                    child.disabled = False
                    if self.state.player_hide == idx:
                        child.style = discord.ButtonStyle.success
                    else:
                        child.style = discord.ButtonStyle.secondary
                continue

            if child.custom_id.startswith("pb_shoot_"):
                idx = int(child.custom_id.split("_")[2])
                if ended:
                    child.disabled = True
                    child.style = discord.ButtonStyle.secondary
                elif not selecting:
                    child.disabled = True
                    child.style = discord.ButtonStyle.secondary
                else:
                    child.disabled = False
                    if self.state.player_shoot == idx:
                        child.style = discord.ButtonStyle.danger
                    else:
                        child.style = discord.ButtonStyle.secondary

    def build_embed(self) -> discord.Embed:
        test_label = " 🧪 TEST GAME 🧪" if self.test_mode else ""
        embed = discord.Embed(
            title=f"Paintball #{self.game_id}{test_label}",
            color=discord.Color.from_str(self.config.get("config", "EMBED_COLOR")),
        )

        if self.state.game_ended:
            embed.description = "Game over."
        elif self.state.phase == PHASE_REVEALING:
            embed.description = self.state.format_round_result()
        elif self.state.ready_to_fire():
            embed.description = (
                f"Aim and move — hiding **{POSITION_NAMES[self.state.player_hide]}**, "
                f"shooting **{POSITION_NAMES[self.state.player_shoot]}**. Press **Fire!**"
            )
        elif self.state.player_hide is not None or self.state.player_shoot is not None:
            parts = []
            if self.state.player_hide is not None:
                parts.append(f"Hide: **{POSITION_NAMES[self.state.player_hide]}**")
            if self.state.player_shoot is not None:
                parts.append(f"Shoot: **{POSITION_NAMES[self.state.player_shoot]}**")
            embed.description = "Aim and move — " + " · ".join(parts)
        else:
            embed.description = "Aim and move — pick where to hide and where to shoot."

        embed.add_field(
            name="You",
            value=format_lives(self.state.player_lives, self.state.max_lives),
            inline=True,
        )
        embed.add_field(
            name="Bot",
            value=format_lives(self.state.bot_lives, self.state.max_lives),
            inline=True,
        )
        embed.add_field(name="Round", value=str(self.state.round), inline=True)

        image_url = self.game_config.get("IMAGE") or self.game_config.get("image_url")
        if image_url:
            embed.set_image(url=image_url)

        logo_url = self.bot.app.embeds.get_logo_url(self.config.get("config", "LOGO"))
        embed.set_footer(text=self.config.get("config", "FOOTER"), icon_url=logo_url)
        return embed

    async def _refresh_message(self, interaction: discord.Interaction):
        self._sync_button_styles()
        embed = self.build_embed()
        target = self.message or interaction.message
        if target:
            try:
                await target.edit(embed=embed, view=self)
            except discord.NotFound:
                pass
            except Exception as e:
                self.logger.error(f"Error refreshing Paintball message: {e}")

    async def _check_valid_game(
        self, interaction: discord.Interaction, *, deferred: bool = False
    ) -> bool:
        if self.test_mode:
            return True
        last_game_id = await self.bot.app.games.get_last_game_id("paintball")
        if self.game_id != last_game_id:
            msg = (
                "`❌` Sorry, but this game has already ended. Please go to the leveling "
                "channel to begin another one!"
            )
            if deferred:
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return False
        return True

    async def _check_cooldown(self, interaction: discord.Interaction, user_id: int) -> bool:
        if user_id in self.cooldowns and datetime.now(timezone.utc) < self.cooldowns[user_id]:
            remaining = (self.cooldowns[user_id] - datetime.now(timezone.utc)).total_seconds()
            await interaction.response.send_message(
                f"`❌` You need to wait {remaining:.2f} seconds before using this button again.",
                ephemeral=True,
            )
            return False
        return True

    async def handle_hide(self, interaction: discord.Interaction, index: int):
        if self.state.game_ended or self.state.phase != PHASE_SELECTING:
            await interaction.response.send_message("`❌` This game has already ended.", ephemeral=True)
            return
        if not await self._check_cooldown(interaction, interaction.user.id):
            return

        await interaction.response.defer()
        if not await self._check_valid_game(interaction, deferred=True):
            return

        self.state.player_hide = index
        self.cooldowns[interaction.user.id] = datetime.now(timezone.utc) + timedelta(
            seconds=self.button_cooldown
        )
        await self._refresh_message(interaction)
        await self._save_state()

    async def handle_shoot(self, interaction: discord.Interaction, index: int):
        if self.state.game_ended or self.state.phase != PHASE_SELECTING:
            await interaction.response.send_message("`❌` This game has already ended.", ephemeral=True)
            return
        if not await self._check_cooldown(interaction, interaction.user.id):
            return

        await interaction.response.defer()
        if not await self._check_valid_game(interaction, deferred=True):
            return

        self.state.player_shoot = index
        self.cooldowns[interaction.user.id] = datetime.now(timezone.utc) + timedelta(
            seconds=self.button_cooldown
        )
        await self._refresh_message(interaction)
        await self._save_state()

    async def handle_fire(self, interaction: discord.Interaction):
        if self.state.game_ended:
            await interaction.response.send_message("`❌` This game has already ended.", ephemeral=True)
            return
        if not self.state.ready_to_fire():
            await interaction.response.send_message(
                "`❌` Pick a hide spot and a shoot target first.",
                ephemeral=True,
            )
            return
        if not await self._check_cooldown(interaction, interaction.user.id):
            return

        try:
            await interaction.response.defer()
        except discord.NotFound:
            return

        if not await self._check_valid_game(interaction, deferred=True):
            return

        async with self._move_lock:
            if self.state.game_ended or not self.state.ready_to_fire():
                return

            self.cooldowns[interaction.user.id] = datetime.now(timezone.utc) + timedelta(
                seconds=self.button_cooldown
            )

            try:
                self.state.phase = PHASE_REVEALING
                bot_hide, bot_shoot = self.state.bot_pick()
                self.state.resolve_round(bot_hide, bot_shoot)
                await self._refresh_message(interaction)
                await self._save_state()

                await asyncio.sleep(self.reveal_delay)

                outcome = self.state.outcome()
                if outcome:
                    await self._finish_game(interaction, outcome)
                    return

                self.state.round += 1
                self.state.phase = PHASE_SELECTING
                self.state.clear_selection()
                await self._refresh_message(interaction)
                await self._save_state()
            except Exception as e:
                self.logger.error(f"Error during Paintball round: {e}")
                import traceback

                self.logger.error(traceback.format_exc())
                if not self.state.game_ended:
                    self.state.phase = PHASE_SELECTING
                    await self._refresh_message(interaction)
                try:
                    await interaction.followup.send(
                        "`❌` Something went wrong on that round. Please try again.",
                        ephemeral=True,
                    )
                except Exception:
                    pass

    async def _finish_game(self, interaction: discord.Interaction, outcome: str):
        self.state.game_ended = True
        self.state.phase = PHASE_ENDED
        self._sync_button_styles()

        current_unix = int(datetime.now(timezone.utc).timestamp())
        repo = GameSessionRepository()
        stats = {
            "rounds": self.state.round,
            "player_lives": self.state.player_lives,
            "bot_lives": self.state.bot_lives,
        }

        if outcome == "won":
            xp = calculate_xp(self.win_min, self.win_max)
            result_msg = f"`✅` You won in **{self.state.round}** round(s)! "
            if self.test_mode:
                result_msg += f"You would have earned `{xp}xp`!"
            else:
                result_msg += f"You earned `{xp}xp`!"
                lvl_mng = LevelingManager(
                    user=interaction.user,
                    channel=interaction.channel,
                    client=self.bot,
                    xp=xp,
                    source="Paintball",
                    game_id=self.game_id,
                )
                await lvl_mng.update()
                await self.bot.app.achievements.check_dm_game_win(
                    interaction.user, "Paintball", interaction.channel, self.bot
                )
                await repo.finish_session(
                    self.game_id,
                    interaction.user.id,
                    "paintball",
                    "won",
                    stats=stats,
                    ended_at=current_unix,
                )
        elif outcome == "lost":
            result_msg = f"`❌` You lost after **{self.state.round}** round(s). The bot got you!"
            if not self.test_mode:
                await repo.finish_session(
                    self.game_id,
                    interaction.user.id,
                    "paintball",
                    "lost",
                    stats=stats,
                    ended_at=current_unix,
                )
        else:
            result_msg = (
                f"`🤝` It's a tie! Both you and the bot were eliminated on round **{self.state.round}**."
            )
            if not self.test_mode:
                await repo.finish_session(
                    self.game_id,
                    interaction.user.id,
                    "paintball",
                    "tied",
                    stats=stats,
                    ended_at=current_unix,
                )

        embed = self.build_embed()
        embed.add_field(name="Result", value=result_msg, inline=False)
        if self.state.last_round:
            embed.description = self.state.format_round_result()

        try:
            await interaction.message.edit(embed=embed, view=self)
        except discord.NotFound:
            pass

        try:
            await interaction.channel.send(result_msg)
        except Exception:
            pass

        await self._save_state()
