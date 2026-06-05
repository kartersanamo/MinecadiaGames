from services.asset_path_service import AssetPathService
import random
from datetime import datetime, timezone
import discord
from games.base.dm_game import DMGame
from core.logging.setup import get_logger
from repositories.game_session_repository import GameSessionRepository
class Hangman(DMGame):
    def __init__(self, bot):
        super().__init__(bot)
        # Support both old and new config structure
        games = self.dm_config.get('GAMES', {})
        if not games:
            games = self.dm_config.get('games', {})
        self.game_config = games.get('Hangman', {})
        self.logger = get_logger("DMGames")
    
    async def _run_game(self, user: discord.User, game_name: str, test_mode: bool = False) -> bool:
        try:
            if test_mode:
                last_game_id = -999999  # Fake game_id for test mode
            else:
                last_game_id = await self.bot.app.games.get_last_game_id('hangman')
                if not last_game_id:
                    return False
            
            # Calculate project root: games/dm/hangman.py -> games/dm/ -> games/ -> project_root/
            project_root = AssetPathService.PROJECT_ROOT
            # Check for both uppercase and lowercase config keys
            # Use same default as Wordle (assets/Configs/data/words.txt)
            words_file_config = self.game_config.get('WORDS_FILE') or self.game_config.get('words_file', 'assets/Configs/data/words.txt')
            if words_file_config.startswith('assets/'):
                words_file = str(project_root / words_file_config)
            else:
                words_file = words_file_config
            
            # Load all words from file (same as Wordle)
            with open(words_file, 'r') as f:
                words = [line.strip().upper() for line in f if line.strip()]
            
            if not words:
                return False
            
            # Filter words to reasonable length for Hangman (4-10 letters for better gameplay)
            # But use all words from the same file as Wordle
            reasonable_words = [w for w in words if 4 <= len(w) <= 10]
            if reasonable_words:
                word = random.choice(reasonable_words)
            else:
                # Fallback to any word if no reasonable length words found
                word = random.choice(words)
            
            if not test_mode and last_game_id != -999999:
                try:
                    repo = GameSessionRepository()
                    session = await repo.get_session(last_game_id, user.id, "hangman")
                    if session and session.get("status") == "started":
                        self.logger.warning(
                            f"User {user.id} already has an active Hangman game {last_game_id}"
                        )
                        return False
                except Exception as e:
                    self.logger.debug(f"Could not check existing Hangman game: {e}")
            
            if not test_mode:
                current_unix = int(datetime.now(timezone.utc).timestamp())
                await GameSessionRepository().start_session(
                    last_game_id,
                    user.id,
                    "hangman",
                    stats={"word": word, "wrong_guesses": 0, "correct_guesses": 0},
                    started_at=current_unix,
                )
            
            max_wrong = self.game_config.get('MAX_WRONG') or self.game_config.get('max_wrong_guesses', 8)
            test_label = " 🧪 TEST GAME 🧪" if test_mode else ""
            
            # Create button view
            from games.dm.hangman.hangman_buttons import HangmanButtons
            view = HangmanButtons(
                last_game_id, 
                self.bot, 
                self.config, 
                self.game_config, 
                self.dm_config, 
                word,
                user.id,
                test_mode=test_mode,
                saved_state=None
            )
            # Register view for persistence across bot restarts
            self.bot.add_view(view)
            
            # Initial word display (all blanks)
            word_display = ' '.join(['_'] * len(word))
            
            embed = discord.Embed(
                title=f"Hangman #{last_game_id}{test_label}",
                description=f"Wrong Guesses: 0/{max_wrong}\nWord: `{word_display}`\nGuessed Letters: `None`\n\nClick a letter button below to guess!",
                color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR'))
            )
            logo_url = self.bot.app.embeds.get_logo_url(self.config.get('config', 'LOGO'))
            embed.set_footer(text=self.config.get('config', 'FOOTER'), icon_url=logo_url)
            
            main_message = await user.send(embed=embed, view=view)
            
            # Store main message reference in view for Z button to update
            view.main_message = main_message
            
            # Create and send Z button in separate message
            from games.dm.hangman.hangman_z_button import HangmanZButton
            z_view = HangmanZButton(last_game_id, self.bot, self.config, self.game_config, self.dm_config, word, user.id, main_message, view, test_mode=test_mode)
            self.bot.add_view(z_view)
            
            # Send message with just Z button (send without embed to avoid description requirement)
            z_message = await user.send(content="\u200b", view=z_view)
            
            # Store references for coordination
            view.z_view = z_view
            view.z_message = z_message
            z_view.z_message = z_message
            z_view.main_view = view  # Store reference to main view for state sharing
            
            # Save initial state
            if not test_mode:
                await view._save_state()
            
            self.logger.info(f"Hangman '{word}' ({user.name}#{user.discriminator})")
            return True
        except Exception as e:
            self.logger.error(f"Hangman error: {e}")
            import traceback
            self.logger.error(f"Full traceback:\n{traceback.format_exc()}")
            return False
