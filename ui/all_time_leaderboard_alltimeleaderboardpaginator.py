from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import discord

from ui.paginator import Paginator

if TYPE_CHECKING:
    from ui.all_time_leaderboard import AllTimeLeaderboardView

class AllTimeLeaderboardPaginator(Paginator):
    def __init__(self, parent_view: AllTimeLeaderboardView, leaderboard_type: str, leaderboard_data: list, message: Optional[discord.Message] = None):
        super().__init__(timeout=900)
        self.parent_view = parent_view
        self.leaderboard_type = leaderboard_type
        self.title = f"🏆 All Time Leaderboard - {parent_view._get_leaderboard_title(leaderboard_type)}"
        self.data = leaderboard_data
        self.sep = 20  # 20 entries per page
        self.ephemeral = True
        self._message = message  # Store message reference for editing
        
        from ui.all_time_leaderboard_alltimeleaderboardselect import AllTimeLeaderboardSelect

        self.add_item(AllTimeLeaderboardSelect(self))
    
    async def update_message(self, interaction: discord.Interaction):
        """Override to use stored message reference if available"""
        self.update_buttons()
        embed = self.create_embed()
        
        # If we have a stored message reference, use it (for the loading message we edited)
        if self._message:
            await self._message.edit(embed=embed, view=self)
        else:
            # Fall back to default behavior
            if self.ephemeral:
                await interaction.edit_original_response(embed=embed, view=self)
            else:
                await interaction.message.edit(embed=embed, view=self)
    
    async def update_leaderboard_type(self, interaction: discord.Interaction, new_type: str):
        """Update the leaderboard type and refresh the display"""
        await interaction.response.defer(ephemeral=True)
        
        # Get new leaderboard data
        leaderboard_data = await self.parent_view.get_all_time_leaderboard(new_type)
        
        if not leaderboard_data:
            await interaction.followup.send("No leaderboard data available.", ephemeral=True)
            return
        
        # Update paginator
        self.leaderboard_type = new_type
        self.title = f"🏆 All Time Leaderboard - {self.parent_view._get_leaderboard_title(new_type)}"
        self.data = leaderboard_data
        self.current_page = 1
        
        # Update display
        self.update_buttons()
        embed = self.create_embed()
        # Use stored message reference if available, otherwise use edit_original_response
        if self._message:
            await self._message.edit(embed=embed, view=self)
        else:
            await interaction.edit_original_response(embed=embed, view=self)

