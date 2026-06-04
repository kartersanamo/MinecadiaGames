from __future__ import annotations

from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from ui.views.logs_view import LogsView


class LogsFilterSelect(discord.ui.Select):
    def __init__(self, parent_view: LogsView):
        self.parent_view = parent_view

        options = [
            discord.SelectOption(
                label="Change Filter Type",
                value="filter_type",
                description="Change what to filter by",
                emoji="🔍",
            ),
            discord.SelectOption(
                label="Change Log Type",
                value="log_type",
                description="Change type of logs to view",
                emoji="📋",
            ),
            discord.SelectOption(
                label="Change Time Range",
                value="time_range",
                description="Change time range for logs",
                emoji="⏰",
            ),
            discord.SelectOption(
                label="View Suspicious Logs",
                value="suspicious",
                description="View detected suspicious activity",
                emoji="⚠️",
            ),
        ]

        super().__init__(
            placeholder="Filter Options...",
            options=options,
            custom_id="logs_filter_select",
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        value = self.values[0]

        if value == "suspicious":
            self.parent_view.log_type = "suspicious"
            await interaction.response.defer(ephemeral=True)
            logs = await self.parent_view.get_logs()
            if logs:
                from ui.views.logs_paginator_view import LogsPaginator

                paginator = LogsPaginator(self.parent_view, logs, "suspicious")
                await paginator.send(interaction)
            else:
                await interaction.followup.send("No suspicious logs found.", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"Filter options will be available in the next update. Current filter: {value}",
                ephemeral=True,
            )
