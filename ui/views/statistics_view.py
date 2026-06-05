
import discord
from core.database.pool import DatabasePool
from core.logging.setup import get_logger
from datetime import datetime, timezone
from ui.paginator import Paginator
from core.errors.decorators import safe_interaction


class StatisticsView(discord.ui.View):
    def __init__(self, bot, config, user_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.config = config
        self.user_id = user_id
        self.logger = get_logger("UI")
        
        # Add game-specific buttons
        self.add_item(self.create_game_button("Trivia", "trivia"))
        self.add_item(self.create_game_button("Math Quiz", "math_quiz"))
        self.add_item(self.create_game_button("Flag Guesser", "flag_guesser"))
        self.add_item(self.create_game_button("Unscramble", "unscramble"))
        self.add_item(self.create_game_button("Emoji Quiz", "emoji_quiz"))
        self.add_item(self.create_game_button("Guess The Number", "guess_the_number"))
        self.add_item(self.create_game_button("Wordle", "wordle"))
        self.add_item(self.create_game_button("TicTacToe", "tictactoe"))
        self.add_item(self.create_game_button("Connect Four", "connect_four"))
        self.add_item(self.create_game_button("Memory", "memory"))
        self.add_item(self.create_game_button("2048", "2048"))
        self.add_item(self.create_game_button("Minesweeper", "minesweeper"))
        self.add_item(self.create_game_button("Hangman", "hangman"))
        self.add_item(self.create_game_button("All Games", "all"))
        self.add_item(self.create_game_button("Monthly Stats", "monthly"))
        self.add_item(self.create_game_button("Game History", "history"))
    
    def create_game_button(self, label: str, game_type: str):
        button = discord.ui.Button(
            label=label,
            style=discord.ButtonStyle.grey,
            custom_id=f"stats_{game_type}_{self.user_id}",
            row=self._get_row_for_button(label)
        )
        button.callback = self.create_callback(game_type)
        return button
    
    def _get_row_for_button(self, label: str) -> int:
        """Distribute buttons across rows"""
        buttons_per_row = 5
        button_index = [
            "Trivia", "Math Quiz", "Flag Guesser", "Unscramble", "Emoji Quiz", "Guess The Number",
            "Wordle", "TicTacToe", "Connect Four", "Memory", "2048", "Minesweeper", "Hangman",
            "All Games", "Monthly Stats", "Game History"
        ].index(label)
        return button_index // buttons_per_row
    
    def create_callback(self, game_type: str):
        @safe_interaction(
            self.logger,
            bot_name="Games",
            component=f"statistics_{game_type}",
        )
        async def callback(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=False)

            if game_type == "all":
                await self.show_all_games_stats(interaction)
            elif game_type == "monthly":
                await self.show_monthly_stats(interaction)
            elif game_type == "history":
                await self.show_game_history(interaction)
            else:
                await self.show_game_specific_stats(interaction, game_type)

        return callback
    
    async def show_all_games_stats(self, interaction: discord.Interaction):
        """Show statistics for all games combined"""
        db = await DatabasePool.get_instance()
        user = self.bot.get_user(self.user_id) or await self.bot.fetch_user(self.user_id)
        
        # Get all game stats
        stats_data = []
        
        # Chat games (from xp_logs)
        chat_games = ["Trivia", "Math Quiz", "Flag Guesser", "Unscramble", "Emoji Quiz", "Guess The Number"]
        for game_name in chat_games:
            game_stats = await db.execute(
                "SELECT COUNT(*) as games, SUM(xp) as total_xp, AVG(xp) as avg_xp FROM xp_logs WHERE user_id = %s AND source = %s",
                (str(self.user_id), game_name)
            )
            if game_stats and game_stats[0]['games']:
                stats_data.append({
                    'game': game_name,
                    'games': game_stats[0]['games'],
                    'total_xp': game_stats[0]['total_xp'] or 0,
                    'avg_xp': game_stats[0]['avg_xp'] or 0,
                    'type': 'chat'
                })
        
        # DM games
        dm_games = [
            ("Wordle", "users_wordle", "won"),
            ("TicTacToe", "users_tictactoe", "won"),
            ("Connect Four", "users_connectfour", "status"),
            ("Memory", "users_memory", "won"),
            ("2048", "users_2048", "status"),
            ("Minesweeper", "users_minesweeper", "won"),
            ("Hangman", "users_hangman", "won")
        ]
        
        for game_name, table_name, status_field in dm_games:
            try:
                if status_field == "won":
                    game_stats = await db.execute(
                        f"SELECT COUNT(*) as games, SUM(CASE WHEN {status_field} = 'Won' THEN 1 ELSE 0 END) as wins FROM {table_name} WHERE user_id = %s",
                        (str(self.user_id),)
                    )
                else:  # status field
                    game_stats = await db.execute(
                        f"SELECT COUNT(*) as games, SUM(CASE WHEN {status_field} = 'Won' THEN 1 ELSE 0 END) as wins FROM {table_name} WHERE user_id = %s",
                        (str(self.user_id),)
                    )
                
                if game_stats and game_stats[0]['games']:
                    wins = game_stats[0]['wins'] or 0
                    total = game_stats[0]['games']
                    win_rate = (wins / total * 100) if total > 0 else 0
                    
                    stats_data.append({
                        'game': game_name,
                        'games': total,
                        'wins': wins,
                        'win_rate': win_rate,
                        'type': 'dm'
                    })
            except Exception as e:
                self.logger.error(f"Error getting stats for {game_name}: {e}")
        
        # Create paginated embed
        if not stats_data:
            await interaction.followup.send("No game statistics found.", ephemeral=False)
            return
        
        # Sort by games played
        stats_data.sort(key=lambda x: x['games'], reverse=True)
        
        # Create pages
        pages = []
        for i in range(0, len(stats_data), 10):
            page_data = stats_data[i:i+10]
            page_text = ""
            for stat in page_data:
                if stat['type'] == 'chat':
                    page_text += (
                        f"**{stat['game']}**\n"
                        f"Games: {stat['games']} | "
                        f"Total XP: {stat['total_xp']:,} | "
                        f"Avg XP: {stat['avg_xp']:.1f}\n\n"
                    )
                else:
                    page_text += (
                        f"**{stat['game']}**\n"
                        f"Games: {stat['games']} | "
                        f"Wins: {stat['wins']} | "
                        f"Win Rate: {stat['win_rate']:.1f}%\n\n"
                    )
            pages.append(page_text)
        
        paginator = Paginator(bot=self.bot)
        paginator.title = f"📊 All Games Statistics - {user.display_name}"
        paginator.data = pages
        paginator.sep = 1
        paginator.ephemeral = False
        
        await paginator.send(interaction)
    
    async def show_monthly_stats(self, interaction: discord.Interaction):
        """Show monthly statistics"""
        from core.logging.setup import get_logger
        logger = get_logger("Commands")
        
        try:
            db = await DatabasePool.get_instance()
            user = self.bot.get_user(self.user_id) or await self.bot.fetch_user(self.user_id)
            
            # Get monthly XP and game counts
            # Use COALESCE to handle both timestamp column and refreshed_at fallback
            # Use LEFT JOIN to handle xp_logs without corresponding games
            monthly_stats = await db.execute(
                """
                SELECT 
                    DATE_FORMAT(FROM_UNIXTIME(COALESCE(xl.timestamp, g.refreshed_at, UNIX_TIMESTAMP())), '%Y-%m') as month,
                    COUNT(*) as games,
                    SUM(xl.xp) as total_xp
                FROM xp_logs xl
                LEFT JOIN games g ON xl.game_id = g.game_id
                WHERE xl.user_id = %s 
                    AND COALESCE(xl.timestamp, g.refreshed_at) IS NOT NULL
                GROUP BY DATE_FORMAT(FROM_UNIXTIME(COALESCE(xl.timestamp, g.refreshed_at)), '%Y-%m')
                ORDER BY month DESC
                LIMIT 12
                """,
                (str(self.user_id),)
            )
            
            if not monthly_stats:
                await interaction.followup.send("No monthly statistics found.", ephemeral=False)
                return
            
            embed = discord.Embed(
                title=f"📅 Monthly Statistics - {user.display_name}",
                color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR')),
                timestamp=datetime.now(timezone.utc)
            )
            
            stats_text = ""
            for stat in monthly_stats:
                stats_text += (
                    f"**{stat['month']}**\n"
                    f"Games: {stat['games']} | "
                    f"Total XP: {int(stat['total_xp']):,}\n\n"
                )
            
            embed.description = stats_text
            embed.set_thumbnail(url=user.display_avatar.url)
            logo_url = self.bot.app.embeds.get_logo_url(self.config.get('config', 'LOGO'))
            embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
            
            await interaction.followup.send(embed=embed, ephemeral=False)
        except Exception as e:
            logger.error(f"Error in show_monthly_stats: {e}")
            import traceback
            logger.error(traceback.format_exc())
            try:
                await interaction.followup.send(
                    f"`❌` An error occurred while fetching monthly statistics. Error: {str(e)}",
                    ephemeral=False
                )
            except Exception:
                pass
    
    async def show_game_history(self, interaction: discord.Interaction):
        """Show recent game history"""
        db = await DatabasePool.get_instance()
        user = self.bot.get_user(self.user_id) or await self.bot.fetch_user(self.user_id)
        
        # Get recent games from xp_logs (join with games table for timestamp)
        recent_games = await db.execute(
            """
            SELECT xl.source, xl.xp, FROM_UNIXTIME(g.refreshed_at) as played_at, xl.game_id
            FROM xp_logs xl
            JOIN games g ON xl.game_id = g.game_id
            WHERE xl.user_id = %s 
            ORDER BY g.refreshed_at DESC 
            LIMIT 50
            """,
            (str(self.user_id),)
        )
        
        if not recent_games:
            await interaction.followup.send("No game history found.", ephemeral=False)
            return
        
        # Create paginated history
        pages = []
        for i in range(0, len(recent_games), 15):
            page_data = recent_games[i:i+15]
            page_text = ""
            for game in page_data:
                played_time = datetime.fromisoformat(str(game['played_at']).replace(' ', 'T'))
                page_text += (
                    f"**{game['source']}** - {game['xp']} XP\n"
                    f"<t:{int(played_time.timestamp())}:R>\n\n"
                )
            pages.append(page_text)
        
        paginator = Paginator(bot=self.bot)
        paginator.title = f"📜 Game History - {user.display_name}"
        paginator.data = pages
        paginator.sep = 1
        paginator.ephemeral = False
        
        await paginator.send(interaction)
    
    async def show_game_specific_stats(self, interaction: discord.Interaction, game_type: str):
        """Show detailed statistics for a specific game"""
        db = await DatabasePool.get_instance()
        user = self.bot.get_user(self.user_id) or await self.bot.fetch_user(self.user_id)
        
        game_name_map = {
            "trivia": "Trivia",
            "math_quiz": "Math Quiz",
            "flag_guesser": "Flag Guesser",
            "unscramble": "Unscramble",
            "emoji_quiz": "Emoji Quiz",
            "guess_the_number": "Guess The Number",
            "wordle": "Wordle",
            "tictactoe": "TicTacToe",
            "connect_four": "Connect Four",
            "memory": "Memory",
            "2048": "2048",
            "minesweeper": "Minesweeper",
            "hangman": "Hangman"
        }
        
        game_name = game_name_map.get(game_type.lower())
        if not game_name:
            await interaction.followup.send("Invalid game type.", ephemeral=False)
            return
        
        # Get stats based on game type
        if game_type.lower() in ["trivia", "math_quiz", "flag_guesser", "unscramble", "emoji_quiz", "guess_the_number"]:
            await self._show_chat_game_stats(interaction, game_name, user)
        else:
            await self._show_dm_game_stats(interaction, game_type.lower(), game_name, user)
    
    async def _show_chat_game_stats(self, interaction: discord.Interaction, game_name: str, user):
        """Show statistics for chat games"""
        db = await DatabasePool.get_instance()
        
        # Get overall stats
        stats = await db.execute(
            """
            SELECT 
                COUNT(*) as total_games,
                SUM(xp) as total_xp,
                AVG(xp) as avg_xp,
                MAX(xp) as max_xp,
                MIN(xp) as min_xp
            FROM xp_logs 
            WHERE user_id = %s AND source = %s
            """,
            (str(self.user_id), game_name)
        )
        
        if not stats or not stats[0]['total_games']:
            await interaction.followup.send(f"No statistics found for {game_name}.", ephemeral=False)
            return
        
        stat = stats[0]
        
        # Calculate win rate (if they got XP, they won)
        win_rate = 100.0  # Chat games: if you got XP, you won
        
        embed = discord.Embed(
            title=f"📊 {game_name} Statistics - {user.display_name}",
            color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR')),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(
            name="Overall Stats",
            value=(
                f"**Total Games:** {stat['total_games']:,}\n"
                f"**Win Rate:** {win_rate:.1f}%\n"
                f"**Total XP:** {stat['total_xp']:,}\n"
                f"**Average XP:** {stat['avg_xp']:.1f}\n"
                f"**Max XP:** {stat['max_xp']}\n"
                f"**Min XP:** {stat['min_xp']}"
            ),
            inline=False
        )
        
        # Get recent games (join with games table for timestamp)
        recent = await db.execute(
            """
            SELECT xl.xp, FROM_UNIXTIME(g.refreshed_at) as played_at
            FROM xp_logs xl
            JOIN games g ON xl.game_id = g.game_id
            WHERE xl.user_id = %s AND xl.source = %s 
            ORDER BY g.refreshed_at DESC 
            LIMIT 10
            """,
            (str(self.user_id), game_name)
        )
        
        if recent:
            recent_text = "\n".join([
                f"{row['xp']} XP - <t:{int(datetime.fromisoformat(str(row['played_at']).replace(' ', 'T')).timestamp())}:R>"
                for row in recent[:5]
            ])
            embed.add_field(
                name="Recent Games",
                value=recent_text,
                inline=False
            )
        
        embed.set_thumbnail(url=user.display_avatar.url)
        logo_url = self.bot.app.embeds.get_logo_url(self.config.get('config', 'LOGO'))
        embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
        await interaction.followup.send(embed=embed, ephemeral=False)
    
    async def _show_dm_game_stats(self, interaction: discord.Interaction, game_type: str, game_name: str, user):
        """Show statistics for DM games"""
        db = await DatabasePool.get_instance()
        
        table_map = {
            "wordle": "users_wordle",
            "tictactoe": "users_tictactoe",
            "connect_four": "users_connectfour",
            "memory": "users_memory",
            "2048": "users_2048",
            "minesweeper": "users_minesweeper",
            "hangman": "users_hangman"
        }
        
        table_name = table_map.get(game_type.lower())
        if not table_name:
            await interaction.followup.send("Invalid game type.", ephemeral=False)
            return
        
        # Get game-specific stats
        if game_type == "wordle":
            await self._show_wordle_stats(interaction, user)
        elif game_type == "tictactoe":
            await self._show_tictactoe_stats(interaction, user)
        elif game_type == "connect_four":
            await self._show_connectfour_stats(interaction, user)
        elif game_type == "memory":
            await self._show_memory_stats(interaction, user)
        elif game_type == "2048":
            await self._show_2048_stats(interaction, user)
        elif game_type == "minesweeper":
            await self._show_minesweeper_stats(interaction, user)
        elif game_type == "hangman":
            await self._show_hangman_stats(interaction, user)
    
    async def _show_wordle_stats(self, interaction: discord.Interaction, user):
        """Show Wordle-specific statistics"""
        db = await DatabasePool.get_instance()
        
        stats = await db.execute(
            """
            SELECT 
                COUNT(*) as total_games,
                SUM(CASE WHEN won = 'Won' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN won = 'Lost' THEN 1 ELSE 0 END) as losses,
                AVG(CASE WHEN won = 'Won' THEN attempts ELSE NULL END) as avg_attempts_won,
                MIN(CASE WHEN won = 'Won' THEN attempts ELSE NULL END) as best_attempts
            FROM users_wordle 
            WHERE user_id = %s
            """,
            (str(self.user_id),)
        )
        
        if not stats or not stats[0]['total_games']:
            await interaction.followup.send("No Wordle statistics found.", ephemeral=False)
            return
        
        stat = stats[0]
        total = stat['total_games']
        wins = stat['wins'] or 0
        losses = stat['losses'] or 0
        win_rate = (wins / total * 100) if total > 0 else 0
        
        embed = discord.Embed(
            title=f"📊 Wordle Statistics - {user.display_name}",
            color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR')),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(
            name="Overall Stats",
            value=(
                f"**Total Games:** {total:,}\n"
                f"**Wins:** {wins}\n"
                f"**Losses:** {losses}\n"
                f"**Win Rate:** {win_rate:.1f}%"
            ),
            inline=False
        )
        
        if stat['avg_attempts_won']:
            embed.add_field(
                name="Performance",
                value=(
                    f"**Average Attempts (Won):** {stat['avg_attempts_won']:.1f}\n"
                    f"**Best Attempts:** {stat['best_attempts'] or 'N/A'}"
                ),
                inline=False
            )
        
        embed.set_thumbnail(url=user.display_avatar.url)
        logo_url = self.bot.app.embeds.get_logo_url(self.config.get('config', 'LOGO'))
        embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
        await interaction.followup.send(embed=embed, ephemeral=False)
    
    async def _show_tictactoe_stats(self, interaction: discord.Interaction, user):
        """Show TicTacToe-specific statistics"""
        db = await DatabasePool.get_instance()
        
        stats = await db.execute(
            """
            SELECT 
                COUNT(*) as total_games,
                SUM(CASE WHEN won = 'Won' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN won = 'Lost' THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN won = 'Tied' THEN 1 ELSE 0 END) as ties
            FROM users_tictactoe 
            WHERE user_id = %s
            """,
            (str(self.user_id),)
        )
        
        if not stats or not stats[0]['total_games']:
            await interaction.followup.send("No TicTacToe statistics found.", ephemeral=False)
            return
        
        stat = stats[0]
        total = stat['total_games']
        wins = stat['wins'] or 0
        losses = stat['losses'] or 0
        ties = stat['ties'] or 0
        win_rate = (wins / total * 100) if total > 0 else 0
        
        embed = discord.Embed(
            title=f"📊 TicTacToe Statistics - {user.display_name}",
            color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR')),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(
            name="Overall Stats",
            value=(
                f"**Total Games:** {total:,}\n"
                f"**Wins:** {wins}\n"
                f"**Losses:** {losses}\n"
                f"**Ties:** {ties}\n"
                f"**Win Rate:** {win_rate:.1f}%"
            ),
            inline=False
        )
        
        embed.set_thumbnail(url=user.display_avatar.url)
        logo_url = self.bot.app.embeds.get_logo_url(self.config.get('config', 'LOGO'))
        embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
        await interaction.followup.send(embed=embed, ephemeral=False)
    
    async def _show_connectfour_stats(self, interaction: discord.Interaction, user):
        """Show Connect Four-specific statistics"""
        db = await DatabasePool.get_instance()
        
        stats = await db.execute(
            """
            SELECT 
                COUNT(*) as total_games,
                SUM(CASE WHEN status = 'Won' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN status = 'Lost' THEN 1 ELSE 0 END) as losses,
                AVG(moves) as avg_moves,
                MIN(moves) as best_moves
            FROM users_connectfour 
            WHERE user_id = %s
            """,
            (str(self.user_id),)
        )
        
        if not stats or not stats[0]['total_games']:
            await interaction.followup.send("No Connect Four statistics found.", ephemeral=False)
            return
        
        stat = stats[0]
        total = stat['total_games']
        wins = stat['wins'] or 0
        losses = stat['losses'] or 0
        win_rate = (wins / total * 100) if total > 0 else 0
        
        embed = discord.Embed(
            title=f"📊 Connect Four Statistics - {user.display_name}",
            color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR')),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(
            name="Overall Stats",
            value=(
                f"**Total Games:** {total:,}\n"
                f"**Wins:** {wins}\n"
                f"**Losses:** {losses}\n"
                f"**Win Rate:** {win_rate:.1f}%"
            ),
            inline=False
        )
        
        if stat['avg_moves']:
            embed.add_field(
                name="Performance",
                value=(
                    f"**Average Moves:** {stat['avg_moves']:.1f}\n"
                    f"**Best (Fewest Moves):** {stat['best_moves'] or 'N/A'}"
                ),
                inline=False
            )
        
        embed.set_thumbnail(url=user.display_avatar.url)
        logo_url = self.bot.app.embeds.get_logo_url(self.config.get('config', 'LOGO'))
        embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
        await interaction.followup.send(embed=embed, ephemeral=False)
    
    async def _show_memory_stats(self, interaction: discord.Interaction, user):
        """Show Memory-specific statistics"""
        db = await DatabasePool.get_instance()
        
        stats = await db.execute(
            """
            SELECT 
                COUNT(*) as total_games,
                SUM(CASE WHEN won = 'Won' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN won = 'Lost' THEN 1 ELSE 0 END) as losses,
                AVG(attempts) as avg_attempts,
                AVG(matches) as avg_matches,
                SUM(xp_earned) as total_xp
            FROM users_memory 
            WHERE user_id = %s
            """,
            (str(self.user_id),)
        )
        
        if not stats or not stats[0]['total_games']:
            await interaction.followup.send("No Memory statistics found.", ephemeral=False)
            return
        
        stat = stats[0]
        total = stat['total_games']
        wins = stat['wins'] or 0
        losses = stat['losses'] or 0
        win_rate = (wins / total * 100) if total > 0 else 0
        
        embed = discord.Embed(
            title=f"📊 Memory Statistics - {user.display_name}",
            color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR')),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(
            name="Overall Stats",
            value=(
                f"**Total Games:** {total:,}\n"
                f"**Wins:** {wins}\n"
                f"**Losses:** {losses}\n"
                f"**Win Rate:** {win_rate:.1f}%\n"
                f"**Total XP:** {stat['total_xp'] or 0:,}"
            ),
            inline=False
        )
        
        if stat['avg_attempts']:
            embed.add_field(
                name="Performance",
                value=(
                    f"**Average Attempts:** {stat['avg_attempts']:.1f}\n"
                    f"**Average Matches:** {stat['avg_matches']:.1f}"
                ),
                inline=False
            )
        
        embed.set_thumbnail(url=user.display_avatar.url)
        logo_url = self.bot.app.embeds.get_logo_url(self.config.get('config', 'LOGO'))
        embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
        await interaction.followup.send(embed=embed, ephemeral=False)
    
    async def _show_2048_stats(self, interaction: discord.Interaction, user):
        """Show 2048-specific statistics"""
        db = await DatabasePool.get_instance()
        
        stats = await db.execute(
            """
            SELECT 
                COUNT(*) as total_games,
                SUM(CASE WHEN status IN ('Won', 'Cashed Out') THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN status = 'Lost' THEN 1 ELSE 0 END) as losses,
                AVG(score) as avg_score,
                MAX(score) as best_score,
                AVG(moves) as avg_moves,
                MAX(highest_tile) as best_tile
            FROM users_2048 
            WHERE user_id = %s
            """,
            (str(self.user_id),)
        )
        
        if not stats or not stats[0]['total_games']:
            await interaction.followup.send("No 2048 statistics found.", ephemeral=False)
            return
        
        stat = stats[0]
        total = stat['total_games']
        wins = stat['wins'] or 0
        losses = stat['losses'] or 0
        win_rate = (wins / total * 100) if total > 0 else 0
        
        embed = discord.Embed(
            title=f"📊 2048 Statistics - {user.display_name}",
            color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR')),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(
            name="Overall Stats",
            value=(
                f"**Total Games:** {total:,}\n"
                f"**Wins:** {wins}\n"
                f"**Losses:** {losses}\n"
                f"**Win Rate:** {win_rate:.1f}%"
            ),
            inline=False
        )
        
        if stat['avg_score']:
            embed.add_field(
                name="Performance",
                value=(
                    f"**Average Score:** {stat['avg_score']:.0f}\n"
                    f"**Best Score:** {stat['best_score'] or 'N/A'}\n"
                    f"**Average Moves:** {stat['avg_moves']:.1f}\n"
                    f"**Best Tile:** {stat['best_tile'] or 'N/A'}"
                ),
                inline=False
            )
        
        embed.set_thumbnail(url=user.display_avatar.url)
        logo_url = self.bot.app.embeds.get_logo_url(self.config.get('config', 'LOGO'))
        embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
        await interaction.followup.send(embed=embed, ephemeral=False)
    
    async def _show_minesweeper_stats(self, interaction: discord.Interaction, user):
        """Show Minesweeper-specific statistics"""
        db = await DatabasePool.get_instance()
        
        stats = await db.execute(
            """
            SELECT 
                COUNT(*) as total_games,
                SUM(CASE WHEN won = 'Won' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN won = 'Lost' THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN won = 'Started' THEN 1 ELSE 0 END) as in_progress,
                AVG(cells_revealed) as avg_cells_revealed,
                MAX(cells_revealed) as best_cells_revealed,
                SUM(mines_found) as total_mines_found
            FROM users_minesweeper 
            WHERE user_id = %s
            """,
            (str(self.user_id),)
        )
        
        if not stats or not stats[0] or stats[0]['total_games'] == 0:
            await interaction.followup.send("No Minesweeper statistics found.", ephemeral=False)
            return
        
        stat = stats[0]
        
        win_rate = (stat['wins'] / stat['total_games'] * 100) if stat['total_games'] > 0 else 0
        
        embed = discord.Embed(
            title=f"📊 Minesweeper Statistics - {user.display_name}",
            color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR')),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(name="Total Games", value=str(stat['total_games']), inline=True)
        embed.add_field(name="Wins", value=str(stat['wins'] or 0), inline=True)
        embed.add_field(name="Losses", value=str(stat['losses'] or 0), inline=True)
        embed.add_field(name="Win Rate", value=f"{win_rate:.1f}%", inline=True)
        embed.add_field(name="In Progress", value=str(stat['in_progress'] or 0), inline=True)
        embed.add_field(name="Avg Cells Revealed", value=f"{stat['avg_cells_revealed']:.1f}" if stat['avg_cells_revealed'] else "0", inline=True)
        embed.add_field(name="Best Cells Revealed", value=str(stat['best_cells_revealed'] or 0), inline=True)
        embed.add_field(name="Total Mines Found", value=str(stat['total_mines_found'] or 0), inline=True)
        
        embed.set_thumbnail(url=user.display_avatar.url)
        logo_url = self.bot.app.embeds.get_logo_url(self.config.get('config', 'LOGO'))
        embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
        
        await interaction.followup.send(embed=embed, ephemeral=False)
    
    async def _show_hangman_stats(self, interaction: discord.Interaction, user):
        """Show Hangman-specific statistics"""
        db = await DatabasePool.get_instance()
        
        stats = await db.execute(
            """
            SELECT 
                COUNT(*) as total_games,
                SUM(CASE WHEN won = 'Won' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN won = 'Lost' THEN 1 ELSE 0 END) as losses,
                AVG(CASE WHEN won = 'Won' THEN wrong_guesses ELSE NULL END) as avg_wrong_won,
                AVG(CASE WHEN won = 'Won' THEN correct_guesses ELSE NULL END) as avg_correct_won
            FROM users_hangman 
            WHERE user_id = %s
            """,
            (str(self.user_id),)
        )
        
        if not stats or not stats[0]['total_games']:
            await interaction.followup.send("No Hangman statistics found.", ephemeral=False)
            return
        
        stat = stats[0]
        total = stat['total_games']
        wins = stat['wins'] or 0
        losses = stat['losses'] or 0
        win_rate = (wins / total * 100) if total > 0 else 0
        
        embed = discord.Embed(
            title=f"📊 Hangman Statistics - {user.display_name}",
            color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR')),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(
            name="Overall Stats",
            value=(
                f"**Total Games:** {total:,}\n"
                f"**Wins:** {wins}\n"
                f"**Losses:** {losses}\n"
                f"**Win Rate:** {win_rate:.1f}%"
            ),
            inline=False
        )
        
        if stat['avg_wrong_won'] is not None:
            embed.add_field(
                name="Performance",
                value=(
                    f"**Average Wrong Guesses (Won):** {stat['avg_wrong_won']:.1f}\n"
                    f"**Average Correct Guesses (Won):** {stat['avg_correct_won']:.1f}"
                ),
                inline=False
            )
        
        embed.set_thumbnail(url=user.display_avatar.url)
        logo_url = self.bot.app.embeds.get_logo_url(self.config.get('config', 'LOGO'))
        embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
        await interaction.followup.send(embed=embed, ephemeral=False)
