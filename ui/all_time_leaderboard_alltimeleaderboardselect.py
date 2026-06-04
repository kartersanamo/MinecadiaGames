from __future__ import annotations

from typing import TYPE_CHECKING

import discord


if TYPE_CHECKING:
    from ui.all_time_leaderboard_alltimeleaderboardpaginator import AllTimeLeaderboardPaginator

class AllTimeLeaderboardSelect(discord.ui.Select):
    def __init__(self, paginator: AllTimeLeaderboardPaginator):
        self.paginator = paginator
        
        options = [
            discord.SelectOption(
                label="All Time XP",
                value="all_time_xp",
                description="Total XP earned across all time",
                emoji="💰"
            ),
            discord.SelectOption(
                label="All Time Level",
                value="all_time_level",
                description="Highest level achieved (calculated from total XP)",
                emoji="⭐"
            ),
            discord.SelectOption(
                label="Trivia Wins",
                value="trivia_wins",
                description="Total Trivia games won",
                emoji="❓"
            ),
            discord.SelectOption(
                label="Math Quiz Wins",
                value="math_quiz_wins",
                description="Total Math Quiz games won",
                emoji="➕"
            ),
            discord.SelectOption(
                label="Flag Guesser Wins",
                value="flag_guesser_wins",
                description="Total Flag Guesser games won",
                emoji="🏳️"
            ),
            discord.SelectOption(
                label="Unscramble Wins",
                value="unscramble_wins",
                description="Total Unscramble games won",
                emoji="🔤"
            ),
            discord.SelectOption(
                label="Emoji Quiz Wins",
                value="emoji_quiz_wins",
                description="Total Emoji Quiz games won",
                emoji="😀"
            ),
            discord.SelectOption(
                label="TicTacToe Wins",
                value="tictactoe_wins",
                description="Total TicTacToe games won",
                emoji="⭕"
            ),
            discord.SelectOption(
                label="Wordle Wins",
                value="wordle_wins",
                description="Total Wordle games won",
                emoji="📝"
            ),
            discord.SelectOption(
                label="Connect Four Wins",
                value="connect_four_wins",
                description="Total Connect Four games won",
                emoji="❌"
            ),
            discord.SelectOption(
                label="Memory Wins",
                value="memory_wins",
                description="Total Memory games won",
                emoji="🧠"
            ),
            discord.SelectOption(
                label="2048 Wins",
                value="2048_wins",
                description="Total 2048 games won (reached 2048 tile)",
                emoji="🔢"
            ),
            discord.SelectOption(
                label="Minesweeper Wins",
                value="minesweeper_wins",
                description="Total Minesweeper games won",
                emoji="💣"
            ),
            discord.SelectOption(
                label="Hangman Wins",
                value="hangman_wins",
                description="Total Hangman games won",
                emoji="🪢"
            ),
            discord.SelectOption(
                label="2048 Best Score",
                value="2048_best_score",
                description="Best score achieved in 2048",
                emoji="🎯"
            ),
        ]
        
        super().__init__(
            placeholder="Select leaderboard type...",
            options=options,
            row=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle select menu selection"""
        leaderboard_type = self.values[0]
        await self.paginator.update_leaderboard_type(interaction, leaderboard_type)

