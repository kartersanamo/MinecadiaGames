from discord.ext import commands
import discord
from core.config.manager import ConfigManager
from core.logging.setup import get_logger
from utils.helpers import get_embed_logo_url
import random


class Tips(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = ConfigManager.get_instance()
        self.logger = get_logger("Tips")
        
        # Channel IDs
        self.COUNTING_CHANNEL_ID = 1455270125384241174
        self.GAMES_CHANNEL_ID = 1456658225964388504
        
        # Message counters (reset after tip is sent)
        self.counting_messages = 0
        self.games_messages = 0
        
        # Tip lists
        self.counting_tips = [
            "💡 **Tip:** Use `/countingstats` to view your counting statistics and see how you rank!",
            "💡 **Tip:** Don't say 2 consecutive numbers in a row - wait for someone else to count!",
            "💡 **Tip:** You can alternate with other players - work together to reach higher numbers!",
            "💡 **Tip:** Counting gives you XP! The more you count, the more XP you earn!",
            "💡 **Tip:** Make sure to count in order - if you break the sequence, the counter resets!",
            "💡 **Tip:** Check the server's highest count with `/countingstats` to see the record!",
            "💡 **Tip:** Every correct count increases your total counts stat - keep counting!",
            "💡 **Tip:** Mistakes are tracked but don't worry - everyone makes them!",
            "💡 **Tip:** The counter resets to 0 if someone breaks the sequence - be careful!",
            "💡 **Tip:** You can see who has the most counts on the server leaderboard!",
            "💡 **Tip:** Counting is a team effort - coordinate with others to reach new heights!",
            "💡 **Tip:** Pay attention to the last number before you count - accuracy matters!",
            "💡 **Tip:** The faster you count, the more XP you can earn in a session!",
            "💡 **Tip:** Use `/countingstats` without mentioning a user to see server-wide stats!",
            "💡 **Tip:** Your highest count is tracked - try to beat your personal record!"
        ]
        
        self.games_tips = [
            # General Tips
            "💡 **Tip:** Use `/statistics` to view detailed stats for all games you've played!",
            "💡 **Tip:** DM games are always available - check the #leveling channel to start one!",
            "💡 **Tip:** All games award XP - the better you perform, the more XP you get!",
            "💡 **Tip:** Use `/test-game` to test any game before playing for real!",
            "💡 **Tip:** Check `/milestones` to see achievements you can unlock!",
            "💡 **Tip:** Practice mode lets you play games without affecting your stats!",
            
            # Trivia Tips
            "💡 **Tip:** In Trivia, read all answer options carefully before choosing!",
            "💡 **Tip:** Trivia questions come from various topics - knowledge helps!",
            "💡 **Tip:** First place in Trivia gets the most XP - be quick and accurate!",
            
            # Math Quiz Tips
            "💡 **Tip:** Math Quiz shows the question type - use it to prepare!",
            "💡 **Tip:** Math problems can be addition, subtraction, multiplication, or division!",
            "💡 **Tip:** Double-check your math calculations before submitting!",
            
            # Flag Guesser Tips
            "💡 **Tip:** Flag Guesser shows country flags - use geography knowledge!",
            "💡 **Tip:** Flag colors and patterns can help identify countries!",
            "💡 **Tip:** Some flags look similar - pay attention to details!",
            
            # Unscramble Tips
            "💡 **Tip:** In Unscramble, look for common letter patterns and prefixes!",
            "💡 **Tip:** Try rearranging vowels and consonants separately first!",
            "💡 **Tip:** Common word endings like -ing, -ed, -er can help solve Unscramble!",
            
            # Emoji Quiz Tips
            "💡 **Tip:** Emoji Quiz emojis represent words, phrases, or concepts!",
            "💡 **Tip:** Think about what the emojis could represent together!",
            "💡 **Tip:** Some emoji quizzes use movie titles, songs, or common phrases!",
            
            # Guess The Number Tips
            "💡 **Tip:** In Guess The Number, use binary search strategy - guess the middle!",
            "💡 **Tip:** The range narrows after each guess - use it to your advantage!",
            "💡 **Tip:** Fewer guesses = more XP bonus in Guess The Number!",
            "💡 **Tip:** Start by guessing 50 to split the range in half!",
            
            # Wordle Tips
            "💡 **Tip:** In Wordle, start with words that have common vowels (A, E, I, O, U)!",
            "💡 **Tip:** Use your first guess to eliminate common letters!",
            "💡 **Tip:** Green = correct letter and position, Yellow = correct letter wrong position!",
            "💡 **Tip:** Gray letters aren't in the word - don't use them again!",
            "💡 **Tip:** Try words with different letter combinations to maximize information!",
            
            # TicTacToe Tips
            "💡 **Tip:** In TicTacToe, control the center for the best advantage!",
            "💡 **Tip:** Block your opponent's winning moves before making your own!",
            "💡 **Tip:** Look for forks - positions where you can win in two ways!",
            "💡 **Tip:** The bot uses strategy - think ahead to counter its moves!",
            
            # Connect Four Tips
            "💡 **Tip:** In Connect Four, control the center columns for better positioning!",
            "💡 **Tip:** Block your opponent's vertical, horizontal, and diagonal threats!",
            "💡 **Tip:** Look for multiple winning opportunities at once!",
            "💡 **Tip:** The bottom row is most important - control it when possible!",
            
            # Memory Tips
            "💡 **Tip:** In Memory, try to remember pairs of cards as you flip them!",
            "💡 **Tip:** Start by flipping cards systematically to build your memory!",
            "💡 **Tip:** Focus on remembering positions rather than trying to match immediately!",
            "💡 **Tip:** Fewer moves = more XP in Memory - plan your flips!",
            
            # 2048 Tips
            "💡 **Tip:** In 2048, pick a corner and stick to it - don't change direction!",
            "💡 **Tip:** Keep your highest tile in a corner and build around it!",
            "💡 **Tip:** Use arrow keys strategically - avoid trapping yourself!",
            "💡 **Tip:** You can cash out in 2048 at any time based on your highest tile!",
            "💡 **Tip:** Higher tiles = more XP when you cash out in 2048!",
            
            # XP & Leveling Tips
            "💡 **Tip:** First place in games gives the most XP - aim for the top!",
            "💡 **Tip:** Double XP games appear randomly - take advantage when they do!",
            "💡 **Tip:** Your level is based on total XP - keep playing to level up!",
            "💡 **Tip:** Check `/level` to see your current level and progress!",
            "💡 **Tip:** Milestones unlock badges that appear on your level card!",
            "💡 **Tip:** Different games award different XP amounts - try them all!",
            
            # Achievement Tips
            "💡 **Tip:** Win games to unlock achievement milestones!",
            "💡 **Tip:** Each game has multiple achievement tiers - keep playing!",
            "💡 **Tip:** Your highest achievement badge shows on leaderboards!",
            "💡 **Tip:** Check `/milestones` to see progress toward next achievements!",
            
            # Game Manager Tips
            "💡 **Tip:** Admins can use `/game-manager` to control game settings!",
            "💡 **Tip:** Use `/logs` to see detailed information about all games!",
            "💡 **Tip:** Right-click any chat game message for admin options!",
            
            # Strategy Tips
            "💡 **Tip:** Practice mode lets you learn games without affecting stats!",
            "💡 **Tip:** Speed matters in chat games - be quick but accurate!",
            "💡 **Tip:** Read game instructions carefully before playing!",
            "💡 **Tip:** Some games have time limits - act fast!",
            "💡 **Tip:** Team up with others in chat games for better coordination!",
            
            # Daily & Streaks
            "💡 **Tip:** Use `/daily` every day to claim your daily XP reward!",
            "💡 **Tip:** Daily streaks increase your XP reward - don't break them!",
            "💡 **Tip:** Longer streaks = more XP from daily rewards!",
            
            # Leaderboard Tips
            "💡 **Tip:** Check the leaderboard in #leveling to see top players!",
            "💡 **Tip:** Your badge appears next to your name on all leaderboards!",
            "💡 **Tip:** All-time leaderboards show historical rankings!",
            
            # Game-Specific Advanced Tips
            "💡 **Tip:** In Trivia, eliminate obviously wrong answers first!",
            "💡 **Tip:** Math Quiz problems get harder as you progress!",
            "💡 **Tip:** Flag Guesser flags are from real countries - study geography!",
            "💡 **Tip:** Unscramble words are common English words!",
            "💡 **Tip:** Emoji Quiz categories include movies, songs, and phrases!",
            "💡 **Tip:** Guess The Number rewards efficiency - fewer guesses = bonus XP!",
            "💡 **Tip:** Wordle has 6 guesses - use them wisely!",
            "💡 **Tip:** TicTacToe against the bot requires strategic thinking!",
            "💡 **Tip:** Connect Four is about controlling the board!",
            "💡 **Tip:** Memory games test your pattern recognition!",
            "💡 **Tip:** 2048 requires planning ahead - think before moving!",
            
            # Community Tips
            "💡 **Tip:** Chat games are community events - everyone can participate!",
            "💡 **Tip:** DM games are personal challenges - play at your own pace!",
            "💡 **Tip:** Share your achievements with others in the server!",
            "💡 **Tip:** Help others learn games - it makes the community better!",
            
            # Performance Tips
            "💡 **Tip:** Practice makes perfect - use practice mode to improve!",
            "💡 **Tip:** Learn from your mistakes - review what went wrong!",
            "💡 **Tip:** Focus on accuracy over speed in some games!",
            "💡 **Tip:** Speed is key in chat games - quick reactions help!",
            
            # Rewards Tips
            "💡 **Tip:** Higher positions in games = more XP rewards!",
            "💡 **Tip:** Double XP games double all rewards - don't miss them!",
            "💡 **Tip:** Consistent playing builds up your total XP over time!",
            "💡 **Tip:** Every game counts toward your overall statistics!",
            
            # Game Mechanics Tips
            "💡 **Tip:** DM games refresh periodically - check #leveling for updates!",
            "💡 **Tip:** Test games don't award real XP - perfect for practice!",
            "💡 **Tip:** All games have time limits - play before they end!",
            
            # Advanced Strategy
            "💡 **Tip:** In competitive games, watch what others do to learn!",
            "💡 **Tip:** Some games reward strategy over speed!",
            "💡 **Tip:** Others reward speed over strategy - know the difference!",
            "💡 **Tip:** Mix of speed and accuracy wins most games!",
            
            # Fun Facts
            "💡 **Tip:** The bot tracks all your game statistics automatically!",
            "💡 **Tip:** Your game history is available in `/statistics`!",
            "💡 **Tip:** Monthly stats show your progress over time!",
            "💡 **Tip:** Past winners are tracked for each game type!",
            
            # More Game-Specific
            "💡 **Tip:** Trivia questions are from various knowledge areas!",
            "💡 **Tip:** Math Quiz covers basic arithmetic operations!",
            "💡 **Tip:** Flag Guesser uses real country flags from around the world!",
            "💡 **Tip:** Unscramble words are everyday vocabulary!",
            "💡 **Tip:** Emoji Quiz can be movies, songs, phrases, or concepts!",
            "💡 **Tip:** Guess The Number uses binary search strategy!",
            "💡 **Tip:** Wordle is a word puzzle game with 5-letter words!",
            "💡 **Tip:** TicTacToe is a classic strategy game!",
            "💡 **Tip:** Connect Four requires 4 in a row to win!",
            "💡 **Tip:** Memory tests your short-term memory skills!",
            "💡 **Tip:** 2048 is a number puzzle game - merge tiles to reach 2048!",
            
            # XP Optimization
            "💡 **Tip:** Play multiple games to maximize XP gains!",
            "💡 **Tip:** First place always gets the most XP!",
            "💡 **Tip:** Even lower positions award XP - every bit counts!",
            "💡 **Tip:** Double XP events are the best time to play!",
            
            # Final Tips
            "💡 **Tip:** Have fun! Games are meant to be enjoyable!",
            "💡 **Tip:** Don't give up - practice improves your skills!",
            "💡 **Tip:** Try all game types to find your favorites!",
            "💡 **Tip:** Compete with friends for friendly competition!",
            "💡 **Tip:** Check your progress regularly with `/statistics`!",
            "💡 **Tip:** Achievements unlock as you play more games!",
            "💡 **Tip:** Your level card shows your top 3 badges!",
            "💡 **Tip:** Leaderboards update in real-time!",
            "💡 **Tip:** All games contribute to your overall progress!",
            "💡 **Tip:** Keep playing to unlock new achievements and badges!"
        ]
        
        # Current tip indices (for rotation)
        self.counting_tip_index = 0
        self.games_tip_index = 0
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for messages in counting and games channels"""
        if message.author.bot:
            return
        
        # Check counting channel
        if message.channel.id == self.COUNTING_CHANNEL_ID:
            self.counting_messages += 1
            if self.counting_messages >= 150:
                await self._send_counting_tip(message.channel)
                self.counting_messages = 0
        
        # Check games channel
        if message.channel.id == self.GAMES_CHANNEL_ID:
            self.games_messages += 1
            if self.games_messages >= 150:
                await self._send_games_tip(message.channel)
                self.games_messages = 0
    
    async def _send_counting_tip(self, channel: discord.TextChannel):
        """Send a counting tip"""
        try:
            # Get next tip (rotate through list)
            tip = self.counting_tips[self.counting_tip_index]
            self.counting_tip_index = (self.counting_tip_index + 1) % len(self.counting_tips)
            
            embed = discord.Embed(
                title="💡 Counting Tip",
                description=tip,
                color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR'))
            )
            embed.set_footer(
                text=self.config.get('config', 'FOOTER'),
                icon_url=get_embed_logo_url(self.config.get('config', 'LOGO'))
            )
            
            await channel.send(embed=embed)
        except Exception as e:
            self.logger.error(f"Error sending counting tip: {e}")
    
    async def _send_games_tip(self, channel: discord.TextChannel):
        """Send a games tip"""
        try:
            # Get next tip (rotate through list)
            tip = self.games_tips[self.games_tip_index]
            self.games_tip_index = (self.games_tip_index + 1) % len(self.games_tips)
            
            embed = discord.Embed(
                title="💡 Game Tip",
                description=tip,
                color=discord.Color.from_str(self.config.get('config', 'EMBED_COLOR'))
            )
            embed.set_footer(
                text=self.config.get('config', 'FOOTER'),
                icon_url=get_embed_logo_url(self.config.get('config', 'LOGO'))
            )
            
            await channel.send(embed=embed)
        except Exception as e:
            self.logger.error(f"Error sending games tip: {e}")


async def setup(bot):
    await bot.add_cog(Tips(bot))

