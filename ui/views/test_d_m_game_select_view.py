from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from core.logging.setup import get_logger

if TYPE_CHECKING:
    from ui.views.test_d_m_game_selector_view import TestDMGameSelectorView


class TestDMGameSelect(discord.ui.Select):
    def __init__(self, parent_view: TestDMGameSelectorView, options: list):
        self.parent_view = parent_view
        super().__init__(
            placeholder="Select a DM game to test...",
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.parent_view.user.id:
            await interaction.response.send_message(
                "This test game selector is not for you!", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        game_name = self.values[0]

        from games.dm.wordle import Wordle
        from games.dm.tictactoe import TicTacToe
        from games.dm.connect_four import ConnectFour
        from games.dm.memory import Memory
        from games.dm.twenty_forty_eight import TwentyFortyEight
        from games.dm.minesweeper import Minesweeper
        from games.dm.hangman import Hangman

        game_map = {
            "wordle": ("Wordle", Wordle),
            "tictactoe": ("TicTacToe", TicTacToe),
            "connect four": ("Connect Four", ConnectFour),
            "memory": ("Memory", Memory),
            "2048": ("2048", TwentyFortyEight),
            "minesweeper": ("Minesweeper", Minesweeper),
            "hangman": ("Hangman", Hangman),
        }

        game_display_name, game_class = game_map.get(game_name.lower(), (None, None))
        if not game_class:
            await interaction.followup.send(
                f"`❌` Unknown DM game: {game_name}", ephemeral=True
            )
            return

        try:
            logger = get_logger("Commands")
            if interaction.client.game_manager and hasattr(
                interaction.client.game_manager, "dm_games"
            ):
                game = interaction.client.game_manager.dm_games.get(game_display_name)
                logger.info(
                    f"Using game_manager instance for {game_display_name}: {id(game)}"
                )
                if not game:
                    logger.warning("Game not found in game_manager, creating new instance")
                    game = game_class(interaction.client)
            else:
                logger.warning("game_manager not available, creating new instance")
                game = game_class(interaction.client)

            success = await game.run(interaction.user, game_display_name, test_mode=True)

            if success:
                await interaction.followup.send(
                    f"`✅` Test {game_display_name} game sent to your DMs!", ephemeral=True
                )
            else:
                error_msg = (
                    game.last_error
                    if hasattr(game, "last_error") and game.last_error
                    else "Failed to start game"
                )
                await interaction.followup.send(f"`❌` {error_msg}", ephemeral=True)
        except Exception as e:
            logger = get_logger("Commands")
            logger.error(f"Error running test DM game {game_name}: {e}")
            import traceback

            logger.error(traceback.format_exc())
            await interaction.followup.send(
                f"`❌` Error running test game: {str(e)}", ephemeral=True
            )
