import asyncio
import random
from datetime import datetime, timezone
from typing import Optional, List
import discord
from games.base.chat_game import ChatGame
from managers.leveling import LevelingManager
from core.logging.setup import get_logger
from services.quote_api_service import fetch_quote_puzzle


def _channel_label(channel: discord.abc.Messageable) -> str:
    if isinstance(channel, discord.DMChannel):
        recipient = channel.recipient
        if recipient:
            return f"DM:{recipient}"
        return "DM"
    return getattr(channel, "name", str(getattr(channel, "id", "unknown")))


class FillInTheBlank(ChatGame):
    def __init__(self, bot):
        super().__init__(bot)
        self.logger = get_logger("ChatGames")

    async def _run_game(
        self,
        channel: discord.abc.Messageable,
        custom_puzzle: Optional[dict] = None,
        xp_multiplier: float = 1.0,
        test_mode: bool = False,
    ) -> Optional[discord.Message]:
        try:
            game_length = self.chat_config.get("GAME_LENGTH") or self.chat_config.get("game_duration", 600)
            current_unix = int(datetime.now(timezone.utc).timestamp())
            end_time = current_unix + game_length

            game_id = await self._create_game_entry(
                "Fill in the Blank", False, test_mode=test_mode, end_time=end_time
            )

            is_dm = isinstance(channel, discord.DMChannel)
            role = None
            if not is_dm:
                guild = self.bot.get_guild(self.config.get("config", "GUILD_ID"))
                if not guild:
                    self.logger.error("Error fetching guild")
                    return None

                role = guild.get_role(self.config.get("config", "GAMES_ROLE"))
                if not role:
                    self.logger.error("Games role not found")
                    return None

            channel_label = _channel_label(channel)

            if custom_puzzle:
                puzzle = custom_puzzle
                self.logger.info(
                    f"Fill in the Blank '{puzzle['correct_answer']}' | '{puzzle.get('author', 'Unknown')}' #{channel_label}"
                )
            else:
                puzzle = await fetch_quote_puzzle()
                if not puzzle:
                    return None
                self.logger.info(
                    f"Fill in the Blank '{puzzle['correct_answer']}' | '{puzzle.get('author', 'Unknown')}' #{channel_label}"
                )

            if xp_multiplier > 1.0:
                double_xp = True
                xp_mult = xp_multiplier
            else:
                double_xp = random.random() <= 0.15
                xp_mult = 2.0 if double_xp else 1.0

            xp_title = ""
            if xp_mult == 2.0:
                xp_title = " (DOUBLE XP)"
            elif xp_mult == 3.0:
                xp_title = " (TRIPLE XP)"
            elif xp_mult > 1.0:
                xp_title = f" ({xp_mult:.1f}x XP)"

            test_label = " 🧪 TEST GAME 🧪" if test_mode else ""

            embed = discord.Embed(
                title=f"Fill in the Blank{test_label}{xp_title}",
                description=f"This game will end <t:{end_time}:R>",
                color=discord.Color.from_str(self.config.get("config", "EMBED_COLOR")),
                timestamp=datetime.now(timezone.utc),
            )
            embed.add_field(name="Quote", value=puzzle["quote_display"], inline=False)

            author_text = puzzle.get("author", "Unknown")
            if puzzle.get("work"):
                author_text = f"{author_text} — *{puzzle['work']}*"
            embed.add_field(name="Author", value=author_text, inline=False)

            view = FillInTheBlankButtons(
                puzzle, xp_mult, game_id, self.bot, self.config, self.chat_config, test_mode=test_mode
            )
            answers = puzzle["answers"][:4]

            items = []
            for index, button in enumerate(view.children):
                if index < len(answers):
                    button.label = answers[index][:80]
                    items.append(button)

            view.clear_items()
            random.shuffle(items)
            for item in items:
                view.add_item(item)

            logo_url = self.bot.app.embeds.get_logo_url(self.config.get("config", "LOGO"))
            embed.set_footer(text=self.config.get("config", "FOOTER"), icon_url=logo_url)

            self.bot.add_view(view)
            message = await channel.send(
                content=role.mention if role else None,
                embed=embed,
                view=view,
            )
            view.message = message

            from services.chat_game_registry import registry

            original_state = {
                "correct_answer": puzzle["correct_answer"],
                "quote_display": puzzle["quote_display"],
                "quote_original": puzzle.get("quote_original", ""),
                "author": puzzle.get("author", ""),
                "answers": puzzle["answers"],
                "embed": {
                    "title": embed.title,
                    "description": embed.description,
                    "fields": [
                        {"name": f.name, "value": f.value, "inline": f.inline} for f in embed.fields
                    ],
                },
            }
            registry.register_game(
                message.id,
                "fill_in_the_blank",
                game_id,
                view,
                original_state,
                xp_mult,
                test_mode,
            )

            view.end_time = end_time
            view.game_id = game_id

            asyncio.create_task(self._game_timer(message, view, end_time, game_id))

            return message
        except Exception as e:
            self.logger.error(f"Fill in the Blank error: {e}")
            return None

    async def _game_timer(self, message: discord.Message, view, end_time: int, game_id: int):
        try:
            current_time = int(datetime.now(timezone.utc).timestamp())
            remaining_time = end_time - current_time

            if remaining_time > 0:
                await asyncio.sleep(remaining_time)

            try:
                if message.components:
                    embed = message.embeds[0] if message.embeds else discord.Embed()
                    embed.description = f"This game ended <t:{end_time}:R>"
                    await message.edit(view=None, embed=embed)

                    await self._update_game_status("Finished")

                    from services.chat_game_registry import registry

                    registry.unregister_game(message.id)

                    self.logger.info(
                        f"Fill in the Blank game ended with {len(view.winners)} winners"
                    )
            except discord.NotFound:
                pass
            except Exception as e:
                self.logger.error(f"Error ending Fill in the Blank game {game_id}: {e}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.error(f"Error in Fill in the Blank timer: {e}")


class FillInTheBlankButtons(discord.ui.View):
    def __init__(
        self, puzzle: dict, xp_multiplier: float, game_id: int, bot, config, chat_config, test_mode: bool = False
    ):
        super().__init__(timeout=None)
        self.correct_answer = puzzle["correct_answer"]
        self.correct_clean = puzzle["correct_answer"].strip("'\"").lower()
        self.all_answers = puzzle["answers"][:4]
        self.xp_multiplier = xp_multiplier
        self.double_xp = xp_multiplier >= 2.0
        self.game_id = game_id
        self.bot = bot
        self.config = config
        self.chat_config = chat_config
        self.test_mode = test_mode
        self.winners: List[dict] = []
        self.message: Optional[discord.Message] = None
        xp_config = chat_config.get("XP", {})
        if not xp_config:
            xp_section = chat_config.get("xp", {})
            xp_config = {
                "XP_ADD": xp_section.get("base", 10),
                "XP_LOWER": xp_section.get("positions", {}),
            }
        self.xp_config = xp_config
        self.winner_count = 0
        self.answer_map = {}
        self.failed_users: set = set()

        for i in range(4):
            answer = self.all_answers[i] if i < len(self.all_answers) else f"Answer {i+1}"
            button = discord.ui.Button(
                label=answer[:80],
                style=discord.ButtonStyle.grey,
                custom_id=f"fill_blank_{i}_{game_id}",
            )
            self.answer_map[f"fill_blank_{i}_{game_id}"] = answer
            button.callback = self.create_callback(answer)
            self.add_item(button)

    def _answer_matches(self, answer: str) -> bool:
        return answer.strip("'\"").lower() == self.correct_clean

    def _get_base_xp_for_position(self, position: int) -> int:
        if position == 1:
            return random.randint(50, 60)
        if position == 2:
            return random.randint(40, 50)
        if position == 3:
            return random.randint(30, 40)
        if position == 4:
            return random.randint(20, 30)
        if position == 5:
            return random.randint(10, 20)

        previous_final_xp = self.winners[-1]["xp"] if self.winners else 20 * self.xp_multiplier
        max_base_xp = max(1, int(previous_final_xp / self.xp_multiplier) - 1)
        min_base_xp = max(1, max_base_xp - 9)

        if min_base_xp > max_base_xp:
            min_base_xp = max_base_xp

        return random.randint(min_base_xp, max_base_xp)

    def _calculate_xp(self, position: int) -> int:
        base_xp = self._get_base_xp_for_position(position)
        xp = int(base_xp * self.xp_multiplier)

        if self.winners:
            xp = min(xp, self.winners[-1]["xp"] - 1)

        return max(0, xp)

    def create_callback(self, answer: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id in self.failed_users:
                from services.chat_game_registry import registry

                if self.message:
                    registry.log_activity(
                        self.message.id,
                        interaction.user.id,
                        "denied",
                        "Already failed - cannot retry",
                        False,
                    )
                await interaction.response.send_message(
                    "You've already answered incorrectly and cannot try again!", ephemeral=True
                )
                return

            from services.chat_game_registry import registry

            if self.message:
                registry.log_activity(
                    self.message.id,
                    interaction.user.id,
                    "click",
                    f"Clicked: {answer[:50]}",
                    True,
                )

            if self._answer_matches(answer):
                if interaction.user.id in [w["user_id"] for w in self.winners]:
                    if self.message:
                        registry.log_activity(
                            self.message.id,
                            interaction.user.id,
                            "denied",
                            "Already won",
                            False,
                        )
                    await interaction.response.send_message(
                        "You've already won this game!", ephemeral=True
                    )
                    return

                self.winner_count += 1
                position = self.winner_count
                xp = self._calculate_xp(position)

                self.winners.append(
                    {
                        "user": interaction.user.mention,
                        "user_id": interaction.user.id,
                        "xp": xp,
                    }
                )

                lvl_mng = LevelingManager(
                    user=interaction.user,
                    channel=interaction.channel,
                    client=self.bot,
                    xp=xp,
                    source="Fill in the Blank",
                    game_id=self.game_id,
                    test_mode=self.test_mode,
                )
                await lvl_mng.update()

                if self.message:
                    registry.log_activity(
                        self.message.id,
                        interaction.user.id,
                        "correct_answer",
                        f"Won {xp} XP (position {position})",
                        True,
                    )

                xp_msg = ""
                if self.xp_multiplier == 2.0:
                    xp_msg = " (2x XP)"
                elif self.xp_multiplier == 3.0:
                    xp_msg = " (3x XP)"
                elif self.xp_multiplier > 1.0:
                    xp_msg = f" ({self.xp_multiplier:.1f}x XP)"

                test_prefix = "🧪 [TEST] " if self.test_mode else ""
                xp_display = (
                    f"would have been awarded `{xp}xp`"
                    if self.test_mode
                    else f"have been awarded `{xp}xp`"
                )

                await interaction.response.send_message(
                    f"`✅` {test_prefix}Correct! You {xp_display}{xp_msg}!",
                    ephemeral=True,
                )

                if self.message:
                    try:
                        embed = self.message.embeds[0]
                        winners_text = "\n".join(f"`+{w['xp']}xp` {w['user']}" for w in self.winners)

                        found_winners_field = False
                        for i, field in enumerate(embed.fields):
                            if field.name == "Winners":
                                embed.set_field_at(
                                    i, name="Winners", value=winners_text, inline=False
                                )
                                found_winners_field = True
                                break
                        if not found_winners_field:
                            embed.add_field(name="Winners", value=winners_text, inline=False)

                        await self.message.edit(embed=embed)
                    except Exception as e:
                        from core.logging.setup import get_logger

                        logger = get_logger("ChatGames")
                        logger.error(f"Error updating winners in embed: {e}")
            else:
                self.failed_users.add(interaction.user.id)

                if self.message:
                    registry.log_activity(
                        self.message.id,
                        interaction.user.id,
                        "wrong_answer",
                        f"Selected: {answer[:50]}",
                        False,
                    )
                await interaction.response.send_message(
                    "`❌` Incorrect answer! You cannot try again.", ephemeral=True
                )

        return callback
