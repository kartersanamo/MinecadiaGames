import ast
import operator
import random
import time
from datetime import timedelta
from typing import Optional
import asyncio
import aiohttp
import discord
from discord.ext import commands
from core.config.manager import ConfigManager
from core.database.pool import DatabasePool
from managers.leveling import LevelingManager
from core.logging.setup import get_logger


class SafeMathEvaluator:
    ALLOWED_OPERATORS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }
    
    @classmethod
    def evaluate(cls, expression: str) -> float:
        try:
            # Handle plain numbers first (simple optimization)
            if expression.isdigit() or (len(expression) > 1 and expression[0] in '+-' and expression[1:].isdigit()):
                return int(expression)
            
            tree = ast.parse(expression, mode="eval")
            return cls._eval_node(tree.body)
        except (ValueError, SyntaxError) as e:
            raise ValueError(f"Invalid expression: {e}")
        except Exception as e:
            raise ValueError(f"Invalid expression: {e}")
    
    @classmethod
    def _eval_node(cls, node):
        # Handle ast.Constant (Python 3.8+)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError("Invalid constant")
        
        # Handle ast.Num for backward compatibility (Python < 3.8)
        if hasattr(ast, 'Num') and isinstance(node, ast.Num):
            if isinstance(node.n, (int, float)):
                return node.n
            raise ValueError("Invalid constant")
        
        if isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in cls.ALLOWED_OPERATORS:
                raise ValueError("Operator not allowed")
            left = cls._eval_node(node.left)
            right = cls._eval_node(node.right)
            return cls.ALLOWED_OPERATORS[op_type](left, right)
        
        if isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in cls.ALLOWED_OPERATORS:
                raise ValueError("Unary operator not allowed")
            operand = cls._eval_node(node.operand)
            return cls.ALLOWED_OPERATORS[op_type](operand)
        
        raise ValueError(f"Invalid expression structure: {type(node).__name__}")


class Counter(commands.Cog):
    COUNTING_CHANNEL_ID = 1455270125384241174
    WEBHOOK_URL = "https://discord.com/api/webhooks/1458445632305107162/0VEqN42iLNShrXNoPlnU9De4yjJ7mz_ldVlPnSGgzB0mEMDAdyopThS4X3XHAhiKQCNV"
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = ConfigManager.get_instance()
        self.db = None
        self.logger = get_logger("Tasks")
        self.last_number: int = 0
        self.last_user_id: Optional[int] = None
        self.last_message_id: Optional[int] = None
        self.last_message_content: Optional[str] = None
        self.last_message_author_name: Optional[str] = None
        self.last_message_author_avatar: Optional[str] = None
        self._initialized = False
        self._deleting_for_edit: bool = False  # Flag to prevent double webhook on edit
        self.user_mistakes = {}  # {user_id: [timestamp, timestamp, ...]} - tracks mistakes with timestamps
        self.muted_users = {}  # {user_id: unmute_time} - tracks muted users and when to unmute them
    
    def _debug_enabled(self) -> bool:
        """Check if counter debugging is enabled in config"""
        try:
            return bool(self.config.get('config', 'COUNTER_DEBUG', False))
        except Exception:
            return False
    
    def _debug_log(self, message: str):
        """Log debug message only if counter debugging is enabled"""
        if self._debug_enabled():
            self.logger.debug(message)
    
    def _calculate_allowed_difference(self, expected_number: int) -> int:
        """Calculate the allowed difference from expected number.
        Returns whichever is larger: 10% of expected number or 3"""
        percent_diff = max(1, int(expected_number * 0.1))  # At least 1 to avoid issues with small numbers
        return max(percent_diff, 3)
    
    def _is_valid_number(self, expected_number: int, actual_number: int) -> bool:
        """Check if the actual number is within the allowed range.
        Returns True if acceptable, False if it's a mistake"""
        if expected_number == actual_number:
            return True
        
        allowed_diff = self._calculate_allowed_difference(expected_number)
        return abs(actual_number - expected_number) <= allowed_diff
    
    def _record_mistake(self, user_id: int) -> int:
        """Record a mistake for a user with current timestamp.
        Returns the number of mistakes in the last minute"""
        current_time = time.time()
        
        if user_id not in self.user_mistakes:
            self.user_mistakes[user_id] = []
        
        # Add the current mistake timestamp
        self.user_mistakes[user_id].append(current_time)
        
        # Clean up mistakes older than 1 minute
        one_minute_ago = current_time - 60
        self.user_mistakes[user_id] = [ts for ts in self.user_mistakes[user_id] if ts > one_minute_ago]
        
        self._debug_log(f"[Counter] User {user_id} mistakes in last minute: {len(self.user_mistakes[user_id])}")
        return len(self.user_mistakes[user_id])
    
    async def _mute_user(self, member: discord.Member, channel: discord.TextChannel, duration_seconds: int = 3600, reason: str = "Counting game violation") -> bool:
        """Mute a user in a specific channel by removing send_messages permission.
        Returns True if successful, False otherwise"""
        try:
            unmute_time = time.time() + duration_seconds
            self.muted_users[member.id] = unmute_time
            
            # Remove send_messages permission for this user in this channel
            await channel.set_permissions(member, send_messages=False, reason=reason)
            
            # Schedule unmute after duration
            asyncio.create_task(self._unmute_user_after_delay(member, channel, duration_seconds))
            
            self.logger.info(f"[Counter] Muted user {member.id} ({member.display_name}) in channel {channel.id} for {duration_seconds} seconds")
            return True
        except discord.Forbidden:
            self.logger.error(f"[Counter] No permission to mute user {member.id}")
            return False
        except discord.HTTPException as e:
            self.logger.error(f"[Counter] Failed to mute user {member.id}: {e}")
            return False
    
    async def _unmute_user_after_delay(self, member: discord.Member, channel: discord.TextChannel, delay_seconds: int):
        """Wait for the specified delay, then unmute the user by removing the permission override"""
        try:
            await asyncio.sleep(delay_seconds)
            
            # Check if the user is still muted
            if member.id in self.muted_users and time.time() >= self.muted_users[member.id]:
                # Remove the permission override to restore default permissions
                try:
                    await channel.delete_permissions(member, reason="Counting game mute expired")
                    self.logger.info(f"[Counter] Unmuted user {member.id} ({member.display_name}) in channel {channel.id}")
                    del self.muted_users[member.id]
                except discord.NotFound:
                    # Permission override already deleted
                    self._debug_log(f"[Counter] Permission override already gone for user {member.id}")
                    if member.id in self.muted_users:
                        del self.muted_users[member.id]
                except (discord.Forbidden, discord.HTTPException) as e:
                    self.logger.error(f"[Counter] Failed to unmute user {member.id}: {e}")
        except asyncio.CancelledError:
            self._debug_log(f"[Counter] Unmute task cancelled for user {member.id}")
        except Exception as e:
            self.logger.error(f"[Counter] Unexpected error in unmute task: {e}", exc_info=True)
    
    async def _check_unmute_expired(self, user_id: int) -> None:
        """Check if a user's mute has expired and remove them from muted_users"""
        if user_id in self.muted_users:
            if time.time() >= self.muted_users[user_id]:
                del self.muted_users[user_id]
                self._debug_log(f"[Counter] User {user_id} mute expired")
    
    def _is_user_muted(self, user_id: int) -> bool:
        """Check if a user is currently muted"""
        if user_id not in self.muted_users:
            return False
        
        if time.time() >= self.muted_users[user_id]:
            del self.muted_users[user_id]
            return False
        
        return True
    
    async def _get_db(self):
        """Get database instance with timeout to prevent hanging"""
        if self.db is None:
            try:
                # Add timeout to prevent hanging if database isn't ready
                self.db = await asyncio.wait_for(DatabasePool.get_instance(), timeout=5.0)
            except asyncio.TimeoutError:
                self.logger.error("[Counter] Database pool not ready after 5 seconds - bot may not be fully initialized")
                raise
            except Exception as e:
                self.logger.error(f"[Counter] Failed to get database instance: {e}")
                raise
        return self.db
    
    async def _send_webhook_message(self, content: str, username: str, avatar_url: Optional[str]) -> Optional[int]:
        """Send a message via webhook with custom username and avatar, returns message ID"""
        payload = {
            "content": content,
            "username": username,
        }
        if avatar_url:
            payload["avatar_url"] = avatar_url
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.WEBHOOK_URL}?wait=true", json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return int(data.get("id", 0))
                    else:
                        self.logger.error(f"Webhook send failed: {resp.status}")
                        return None
        except Exception as e:
            self.logger.error(f"Webhook error: {e}")
            return None
    
    async def cog_load(self):
        """Called when the cog is loaded"""
        self.logger.info("[Counter] Counter cog loaded")
        # Try to load immediately if bot is already ready
        if self.bot.is_ready():
            if not self._initialized:
                self._initialized = True
                self.logger.info("[Counter] Bot already ready, loading last number...")
                await self._load_last_number()
    
    @commands.Cog.listener()
    async def on_ready(self):
        if not self._initialized:
            self._initialized = True
            self.logger.info("[Counter] Bot ready, Counter cog initialized, loading last number...")
            await self._load_last_number()
    
    async def _load_last_number(self):
        try:
            guild = self.bot.guilds[0] if self.bot.guilds else None
            if not guild:
                self.logger.warning("[Counter] No guild found, cannot load last number")
                return
            
            try:
                db = await asyncio.wait_for(self._get_db(), timeout=5.0)
            except asyncio.TimeoutError:
                self.logger.warning(f"[Counter] Database not ready after 5 seconds - using default last_number=0")
                self.last_number = 0
                self.last_user_id = None
                return
            except Exception as db_e:
                self.logger.error(f"[Counter] Failed to get database connection: {db_e}")
                self.last_number = 0
                self.last_user_id = None
                self.logger.warning("[Counter] Using default last_number=0 due to database error")
                return
            
            try:
                rows = await asyncio.wait_for(
                    db.execute(
                        "SELECT last_number FROM counting_server WHERE guild_id = %s",
                        (str(guild.id),)
                    ),
                    timeout=3.0
                )
                
                if rows:
                    self.last_number = int(rows[0].get("last_number", 0))
                    self.last_user_id = None
                    self.logger.info(f"[Counter] Restored count: {self.last_number}")
                else:
                    self.last_number = 0
                    self.last_user_id = None
                    self.logger.info("[Counter] No saved count found, starting at 0")
            except Exception as query_e:
                self.logger.error(f"[Counter] Database query error: {query_e}")
                self.last_number = 0
                self.last_user_id = None
                self.logger.warning("[Counter] Using default last_number=0 due to query error")
        except Exception as e:
            self.logger.error(f"[Counter] Load error: {e}", exc_info=True)
            self.last_number = 0
            self.last_user_id = None
    
    async def _reset_counter(self, message: discord.Message, reason: str):
        """Reset the counter due to an error and notify the user"""
        try:
            guild_id = message.guild.id
            user_id = message.author.id
            
            self.logger.info(f"[Counter] Resetting counter: {reason} (message: {message.id})")
            
            # Update database (with timeout to prevent hanging)
            try:
                db = await asyncio.wait_for(self._get_db(), timeout=3.0)
                await asyncio.wait_for(
                    db.execute(
                        "UPDATE counting_users SET mistakes = mistakes + 1 WHERE guild_id = %s AND user_id = %s",
                        (str(guild_id), str(user_id))
                    ),
                    timeout=3.0
                )
                self._debug_log(f"[Counter] Updated mistakes for user {user_id}")
                
                await asyncio.wait_for(
                    db.execute(
                        "INSERT INTO counting_server (guild_id, last_number) VALUES (%s, %s) ON DUPLICATE KEY UPDATE last_number = %s",
                        (str(guild_id), 0, 0)
                    ),
                    timeout=3.0
                )
                self._debug_log(f"[Counter] Reset counting_server for guild {guild_id}")
            except asyncio.TimeoutError:
                self.logger.warning(f"[Counter] Database operation timed out in reset_counter - continuing without DB update")
                # Continue anyway - reset in-memory state
            except Exception as db_e:
                self.logger.error(f"[Counter] Database error in reset_counter: {db_e}", exc_info=True)
                # Continue anyway - reset in-memory state
            
            # Reset in-memory state
            self.last_number = 0
            self.last_user_id = None
            self.last_message_id = None
            self.last_message_content = None
            self.last_message_author_name = None
            self.last_message_author_avatar = None
            
            # Add reaction (before or after delete, doesn't matter if delete fails)
            try:
                await message.add_reaction("❌")
                self._debug_log(f"[Counter] Added ❌ reaction to message {message.id}")
            except (discord.NotFound, discord.Forbidden, discord.HTTPException) as react_e:
                self._debug_log(f"[Counter] Could not add reaction (message may be deleted): {react_e}")
            
            # Send reply notification (try to reply, fallback to regular send if message was deleted)
            try:
                try:
                    await message.reply(
                        f"❌ {message.author.mention} **Count reset!** {reason}\n"
                        f"-# The count is now **0**. Start again with **1**.",
                        mention_author=True
                    )
                except (discord.NotFound, discord.HTTPException):
                    # Message might have been deleted, send as regular message instead
                    await message.channel.send(
                        f"❌ {message.author.mention} **Count reset!** {reason}\n"
                        f"-# The count is now **0**. Start again with **1**."
                    )
                self._debug_log(f"[Counter] Sent reset notification message")
            except Exception as reply_e:
                self.logger.error(f"[Counter] Failed to send reset notification: {reply_e}", exc_info=True)
                
        except Exception as e:
            self.logger.error(f"[Counter] Unexpected error in _reset_counter: {e}", exc_info=True)
    
    @commands.Cog.listener("on_message")
    async def on_message(self, message: discord.Message):
        try:
            if message.author.bot:
                return
            
            if message.channel.id != self.COUNTING_CHANNEL_ID:
                return
            
            # Check if user is muted
            if self._is_user_muted(message.author.id):
                remaining_time = self.muted_users[message.author.id] - time.time()
                minutes = int(remaining_time // 60)
                self.logger.info(f"[Counter] Muted user {message.author.id} tried to send message")
                try:
                    await message.delete()
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass
                return
            
            # Delete forwarded messages
            if hasattr(message.flags, 'forwarded') and message.flags.forwarded:
                try:
                    await message.delete()
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass
                return
            
            if message.attachments or message.embeds:
                return
            
            content = message.content.strip()
            self.logger.info(f"[Counter] Processing message: '{content}' from {message.author.name} (ID: {message.author.id}), current last_number: {self.last_number}")
            
            # Try to evaluate as math expression first
            result = None
            try:
                result = SafeMathEvaluator.evaluate(content)
                self.logger.info(f"[Counter] Evaluated '{content}' to {result} (type: {type(result)})")
            except Exception as e:
                self.logger.warning(f"[Counter] Failed to evaluate '{content}' as math expression: {e}")
                # Try as plain number string as fallback
                try:
                    # Check if it's a plain number (digits only, possibly with sign)
                    if content and (content.isdigit() or (len(content) > 1 and content[0] in '+-' and content[1:].isdigit())):
                        result = int(content)
                        self.logger.info(f"[Counter] Parsed '{content}' as plain number: {result}")
                    else:
                        self.logger.info(f"[Counter] '{content}' is not a valid number or expression, ignoring")
                        return  # Not a valid number or expression
                except (ValueError, IndexError, AttributeError) as e2:
                    self.logger.info(f"[Counter] Failed to parse '{content}' as number: {e2}")
                    return  # Not a number
            
            if result is None:
                self.logger.warning(f"[Counter] Result is None for '{content}'")
                return
            
            # Validate result
            if not isinstance(result, (int, float)):
                self.logger.warning(f"[Counter] Result is not a number: {result} (type: {type(result)})")
                return
            
            if not float(result).is_integer():
                self.logger.info(f"[Counter] Result is not an integer: {result}, ignoring")
                return
            
            result = int(result)
            self.logger.info(f"[Counter] Validated number: {result}, expected: {self.last_number + 1}, last_user_id: {self.last_user_id}")
            
            guild_id = message.guild.id
            user_id = message.author.id
            expected_number = self.last_number + 1
            
            if self.last_user_id == user_id:
                self.logger.info(f"[Counter] User {user_id} tried to count twice in a row")
                mistake_count = self._record_mistake(user_id)
                self._debug_log(f"[Counter] Double count is mistake {mistake_count}/3")
                
                try:
                    if mistake_count >= 3:
                        # 3rd mistake - mute for 1 hour
                        self.logger.warning(f"[Counter] User {user_id} reached 3 mistakes in 1 minute, muting for 1 hour")
                        await self._reset_counter(message, "You made **3 mistakes in 1 minute**! You are muted for **1 hour**.")
                        if message.guild:
                            member = message.guild.get_member(user_id)
                            if member:
                                await self._mute_user(
                                    member,
                                    message.channel,
                                    duration_seconds=3600,
                                    reason="3 mistakes in 1 minute"
                                )
                    else:
                        # Record mistake but don't mute yet
                        await self._reset_counter(message, f"You can't count **twice in a row**. (Mistake {mistake_count}/3)")
                except Exception as e:
                    self.logger.error(f"[Counter] Error in reset_counter (double count): {e}", exc_info=True)
                return
            
            if result != expected_number:
                # Check if it's a valid number (within allowed difference)
                if self._is_valid_number(expected_number, result):
                    # Within acceptable range, just reset without muting
                    self.logger.info(f"[Counter] Number {result} is within acceptable range of {expected_number}")
                    try:
                        await self._reset_counter(
                            message,
                            f"Expected **{expected_number}**, but got **{result}**."
                        )
                    except Exception as e:
                        self.logger.error(f"[Counter] Error in reset_counter (acceptable range): {e}", exc_info=True)
                else:
                    # Outside acceptable range - IMMEDIATELY MUTE for 1 hour
                    self.logger.warning(f"[Counter] User {user_id} entered number too far from expected: {result} vs {expected_number}")
                    
                    try:
                        await self._reset_counter(
                            message,
                            f"Expected **{expected_number}**, but got **{result}** (too far away)! You are muted for **1 hour**."
                        )
                        # Mute the user immediately
                        if message.guild:
                            member = message.guild.get_member(user_id)
                            if member:
                                await self._mute_user(
                                    member,
                                    message.channel,
                                    duration_seconds=3600,
                                    reason="Number too far from expected"
                                )
                    except Exception as e:
                        self.logger.error(f"[Counter] Error handling large mistake mute: {e}", exc_info=True)
                return
            
            self.logger.info(f"[Counter] ✅ Correct number {result}! Updating counter...")
            
            # Update in-memory state FIRST (before any async operations)
            self.last_number = result
            self.last_user_id = user_id
            self.last_message_id = message.id
            self.last_message_content = message.content.strip()
            self.last_message_author_name = message.author.display_name
            self.last_message_author_avatar = message.author.display_avatar.url if message.author.display_avatar else None
            
            # Add reaction FIRST (before database operations, so it happens even if DB hangs)
            try:
                await message.add_reaction("✅")
                self._debug_log(f"[Counter] Added ✅ reaction to message {message.id}")
            except Exception as react_e:
                self.logger.error(f"[Counter] Failed to add reaction: {react_e}", exc_info=True)
            
            # Update database (with timeout to prevent hanging) - do this AFTER reaction
            try:
                db = await asyncio.wait_for(self._get_db(), timeout=3.0)
                await asyncio.wait_for(
                    db.execute(
                        "INSERT INTO counting_users (guild_id, user_id, total_counts, highest_count, mistakes) "
                        "VALUES (%s, %s, 1, %s, 0) "
                        "ON DUPLICATE KEY UPDATE "
                        "total_counts = total_counts + 1, "
                        "highest_count = GREATEST(highest_count, %s)",
                        (str(guild_id), str(user_id), result, result)
                    ),
                    timeout=3.0
                )
                self._debug_log(f"[Counter] Updated counting_users for user {user_id}")
                
                await asyncio.wait_for(
                    db.execute(
                        "INSERT INTO counting_server (guild_id, last_number, total_counts, highest_count) "
                        "VALUES (%s, %s, 1, %s) "
                        "ON DUPLICATE KEY UPDATE "
                        "last_number = %s, "
                        "total_counts = total_counts + 1, "
                        "highest_count = GREATEST(highest_count, %s)",
                        (str(guild_id), result, result, result, result)
                    ),
                    timeout=3.0
                )
                self._debug_log(f"[Counter] Updated counting_server for guild {guild_id}")
            except asyncio.TimeoutError:
                self.logger.warning(f"[Counter] Database operation timed out - continuing without DB update")
                # Continue anyway - state is updated in memory
            except Exception as db_e:
                self.logger.error(f"[Counter] Database error while updating counter: {db_e}", exc_info=True)
                # Continue anyway - state is updated in memory
            
            # Award XP randomly
            if random.random() < 0.25:
                try:
                    lvl = LevelingManager(
                        user=message.author,
                        channel=message.channel,
                        client=self.bot,
                        xp=1,
                        source="Counting",
                        game_id=-1
                    )
                    await lvl.update()
                    self._debug_log(f"[Counter] Awarded XP to user {user_id}")
                except Exception as xp_e:
                    self.logger.error(f"[Counter] Failed to award XP: {xp_e}", exc_info=True)
                    
        except Exception as e:
            self.logger.error(f"[Counter] Unexpected error in on_message handler: {e}", exc_info=True)
    
    @commands.Cog.listener("on_message_edit")
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if after.channel.id != self.COUNTING_CHANNEL_ID:
            return
        
        if after.author.bot:
            return
        
        # Check if this is the most recent counted message
        if before.id == self.last_message_id and self.last_message_content:
            # Store the info before deleting
            original_content = self.last_message_content
            author_name = before.author.display_name
            author_avatar = before.author.display_avatar.url if before.author.display_avatar else None
            
            # Set flag to prevent on_message_delete from also sending a webhook
            self._deleting_for_edit = True
            try:
                await after.delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass
            finally:
                self._deleting_for_edit = False
            
            # Resend via webhook
            new_msg_id = await self._send_webhook_message(original_content, author_name, author_avatar)
            if new_msg_id:
                self.last_message_id = new_msg_id
                # Add the check reaction to the webhook message
                try:
                    channel = self.bot.get_channel(self.COUNTING_CHANNEL_ID)
                    if channel:
                        webhook_msg = await channel.fetch_message(new_msg_id)
                        await webhook_msg.add_reaction("✅")
                except Exception as e:
                    self.logger.error(f"Failed to add reaction to webhook message: {e}")
        else:
            # Not the most recent count, just delete (no webhook needed)
            self._deleting_for_edit = True
            try:
                await after.delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass
            finally:
                self._deleting_for_edit = False
    
    @commands.Cog.listener("on_message_delete")
    async def on_message_delete(self, message: discord.Message):
        if message.channel.id != self.COUNTING_CHANNEL_ID:
            return
        
        # Skip if this delete was triggered by on_message_edit (it handles the webhook itself)
        if self._deleting_for_edit:
            return
        
        # Check if this is the most recent counted message
        if message.id == self.last_message_id and self.last_message_content:
            # Resend via webhook with the original author's info
            new_msg_id = await self._send_webhook_message(
                self.last_message_content,
                self.last_message_author_name,
                self.last_message_author_avatar
            )
            if new_msg_id:
                self.last_message_id = new_msg_id
                # Add the check reaction to the webhook message
                try:
                    channel = self.bot.get_channel(self.COUNTING_CHANNEL_ID)
                    if channel:
                        webhook_msg = await channel.fetch_message(new_msg_id)
                        await webhook_msg.add_reaction("✅")
                except Exception as e:
                    self.logger.error(f"Failed to add reaction to webhook message: {e}")
    
    @commands.command(name="resetcount")
    @commands.has_permissions(administrator=True)
    async def reset_count(self, ctx: commands.Context, value: int = 0):
        guild_id = ctx.guild.id
        
        self.last_number = value
        self.last_user_id = None
        
        db = await self._get_db()
        await db.execute(
            "INSERT INTO counting_server (guild_id, last_number) VALUES (%s, %s) ON DUPLICATE KEY UPDATE last_number = %s",
            (str(guild_id), value, value)
        )
        
        await ctx.send(f"🔁 Counter reset to `{value}`.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Counter(bot))

