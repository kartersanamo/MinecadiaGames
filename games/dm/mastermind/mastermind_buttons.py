from datetime import datetime, timedelta, timezone

import discord

from core.logging.setup import get_logger
from games.dm.mastermind.mastermind_engine import (
    DEFAULT_COLORS,
    MastermindState,
    calculate_win_xp,
)
from managers.leveling import LevelingManager
from repositories.game_session_repository import GameSessionRepository


class MastermindButtons(discord.ui.View):
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
        self.colors = game_config.get("colors") or DEFAULT_COLORS
        self.cooldowns = {}
        self.logger = get_logger("DMGames")
        self.player_id = None
        self.message = None

        max_guesses = int(game_config.get("max_guesses", 8))
        code_length = int(game_config.get("code_length", 4))
        num_colors = int(game_config.get("num_colors", len(self.colors)))
        self.colors = self.colors[:num_colors]

        if saved_state:
            self.state = MastermindState.from_dict(saved_state, colors=self.colors)
        else:
            self.state = MastermindState.new(
                max_guesses=max_guesses,
                code_length=code_length,
                num_colors=num_colors,
            )

        xp_cfg = game_config.get("xp") or game_config.get("WIN_XP") or {}
        self.win_min = int(xp_cfg.get("win_min") or xp_cfg.get("LOWER", 80))
        self.win_max = int(xp_cfg.get("win_max") or xp_cfg.get("UPPER", 240))

        for color_idx in range(len(self.colors)):
            button = discord.ui.Button(
                label=self.colors[color_idx],
                style=discord.ButtonStyle.secondary,
                custom_id=f"mm_{color_idx}_{game_id}",
                row=color_idx // 3,
            )
            button.callback = self._make_color_callback(color_idx)
            self.add_item(button)

        undo_button = discord.ui.Button(
            label="Undo",
            emoji="↩️",
            style=discord.ButtonStyle.grey,
            custom_id=f"mm_undo_{game_id}",
            row=2,
        )
        undo_button.callback = self._undo_callback
        self.add_item(undo_button)

        self._sync_button_states()

    def _make_color_callback(self, color_idx: int):
        async def callback(interaction: discord.Interaction):
            await self.handle_color_pick(interaction, color_idx)

        return callback

    async def _undo_callback(self, interaction: discord.Interaction):
        if self.state.game_ended:
            await interaction.response.send_message(
                "`❌` This game has already ended.",
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

        if not self.state.undo_peg():
            await interaction.response.send_message(
                "`❌` Nothing to undo on the current row.",
                ephemeral=True,
            )
            return

        try:
            await interaction.response.defer()
        except discord.NotFound:
            return

        if not await self._check_valid_game(interaction, deferred=True):
            return

        self.cooldowns[user_id] = datetime.now(timezone.utc) + timedelta(
            seconds=self.button_cooldown
        )
        await self._refresh_message(interaction)
        await self._save_state()

    def _get_state(self) -> dict:
        data = self.state.to_dict()
        data["game_ended"] = self.state.game_ended
        return data

    async def _save_state(self):
        if self.test_mode or self.game_id == -999999 or not self.player_id:
            return
        try:
            await self.bot.app.game_state.save(
                "mastermind", self.game_id, self.player_id, self._get_state(), self.test_mode
            )
        except Exception as e:
            self.logger.error(f"Error saving Mastermind game state: {e}")

    def _sync_button_states(self):
        for child in self.children:
            if not isinstance(child, discord.ui.Button):
                continue
            if self.state.game_ended:
                child.disabled = True
                continue
            if child.custom_id.startswith("mm_undo_"):
                child.disabled = not self.state.current_guess
            else:
                child.disabled = len(self.state.current_guess) >= self.state.code_length

    def build_embed(self, title_suffix: str = "") -> discord.Embed:
        test_label = " 🧪 TEST GAME 🧪" if self.test_mode else ""
        reveal = self.state.game_ended
        parts = self.state.render_embed_parts(self.colors, reveal_secret=reveal)
        embed = discord.Embed(
            title=f"Mastermind #{self.game_id}{test_label}{title_suffix}",
            description=parts["description"],
            color=discord.Color.from_str(self.config.get("config", "EMBED_COLOR")),
        )
        embed.add_field(name="Guesses", value=parts["guesses"], inline=True)
        embed.add_field(name="Feedback", value=parts["feedback"], inline=True)
        if not self.state.game_ended:
            embed.add_field(
                name="How to play",
                value=(
                    "Pick colors below to fill the current row left to right. "
                    "When a row is full, feedback appears automatically: "
                    "⚫ = correct color and position, ⚪ = correct color wrong position."
                ),
                inline=False,
            )
        logo_url = self.bot.app.embeds.get_logo_url(self.config.get("config", "LOGO"))
        embed.set_footer(text=self.config.get("config", "FOOTER"), icon_url=logo_url)
        return embed

    async def _refresh_message(self, interaction: discord.Interaction):
        self._sync_button_states()
        embed = self.build_embed()
        target = self.message or interaction.message
        if target:
            try:
                await target.edit(embed=embed, view=self)
            except discord.NotFound:
                pass
            except Exception as e:
                self.logger.error(f"Error refreshing Mastermind message: {e}")

    async def _check_valid_game(
        self, interaction: discord.Interaction, *, deferred: bool = False
    ) -> bool:
        if self.test_mode:
            return True
        last_game_id = await self.bot.app.games.get_last_game_id("mastermind")
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

    async def handle_color_pick(self, interaction: discord.Interaction, color_idx: int):
        if self.state.game_ended:
            await interaction.response.send_message(
                "`❌` This game has already ended.",
                ephemeral=True,
            )
            return

        if len(self.state.current_guess) >= self.state.code_length:
            await interaction.response.send_message(
                "`❌` This row is full. Wait for feedback on your last guess.",
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

        try:
            await interaction.response.defer()
        except discord.NotFound:
            return

        if not await self._check_valid_game(interaction, deferred=True):
            return

        self.cooldowns[user_id] = datetime.now(timezone.utc) + timedelta(
            seconds=self.button_cooldown
        )

        row_completed = self.state.place_peg(color_idx)
        await self._refresh_message(interaction)

        if row_completed and self.state.game_ended:
            await self._finish_game(interaction)
            return

        await self._save_state()

    async def _finish_game(self, interaction: discord.Interaction):
        self._sync_button_states()
        current_unix = int(datetime.now(timezone.utc).timestamp())
        repo = GameSessionRepository()
        guesses_used = self.state.guesses_used
        stats = {"guesses_used": guesses_used}

        if self.state.won:
            xp = calculate_win_xp(
                guesses_used,
                self.state.max_guesses,
                self.win_min,
                self.win_max,
            )
            if self.test_mode:
                result_msg = (
                    f"`✅` You cracked the code in **{guesses_used}** "
                    f"guess{'es' if guesses_used != 1 else ''}! "
                    f"You would have earned `{xp}xp`!"
                )
            else:
                result_msg = (
                    f"`✅` You cracked the code in **{guesses_used}** "
                    f"guess{'es' if guesses_used != 1 else ''}! "
                    f"You earned `{xp}xp`!"
                )
                lvl_mng = LevelingManager(
                    user=interaction.user,
                    channel=interaction.channel,
                    client=self.bot,
                    xp=xp,
                    source="Mastermind",
                    game_id=self.game_id,
                )
                await lvl_mng.update()
                await self.bot.app.achievements.check_dm_game_win(
                    interaction.user, "Mastermind", interaction.channel, self.bot
                )
                await repo.finish_session(
                    self.game_id,
                    interaction.user.id,
                    "mastermind",
                    "won",
                    stats=stats,
                    ended_at=current_unix,
                )
        else:
            result_msg = (
                f"`❌` Out of guesses! The secret code was revealed above."
            )
            if not self.test_mode:
                await repo.finish_session(
                    self.game_id,
                    interaction.user.id,
                    "mastermind",
                    "lost",
                    stats=stats,
                    ended_at=current_unix,
                )

        embed = self.build_embed()
        embed.add_field(name="Result", value=result_msg, inline=False)
        try:
            target = self.message or interaction.message
            if target:
                await target.edit(embed=embed, view=self)
        except discord.NotFound:
            pass

        try:
            await interaction.channel.send(result_msg)
        except Exception:
            pass

        await self._save_state()
