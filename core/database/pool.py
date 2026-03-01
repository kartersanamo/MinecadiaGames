import os
import aiomysql
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
import asyncio
from ..config.manager import ConfigManager


def _get_db_config() -> Dict[str, Any]:
    """Build database config from .env (DB_*) or fall back to config file."""
    if os.getenv('DB_HOST'):
        port = os.getenv('DB_PORT', '3306')
        try:
            port = int(port)
        except ValueError:
            port = 3306
        autocommit = os.getenv('DB_AUTOCOMMIT', 'true').lower() in ('1', 'true', 'yes')
        return {
            'host': os.getenv('DB_HOST', '127.0.0.1'),
            'port': port,
            'user': os.getenv('DB_USER', ''),
            'password': os.getenv('DB_PASSWORD', ''),
            'database': os.getenv('DB_NAME', '') or os.getenv('DB_DATABASE', ''),
            'autocommit': autocommit,
        }
    config = ConfigManager.get_instance()
    return config.get('config', 'DATABASE_CONFIG') or {}


class DatabasePool:
    _instance: Optional['DatabasePool'] = None
    _lock: Optional[asyncio.Lock] = None
    _initializing: Optional[asyncio.Event] = None
    _init_task: Optional[asyncio.Task] = None
    
    def __init__(self, min_size: int = 2, max_size: int = 10):
        self.min_size = min_size
        self.max_size = max_size
        self.pool: Optional[aiomysql.Pool] = None
        self.config = ConfigManager.get_instance()
        self._initialized = False
        self._init_lock = asyncio.Lock()  # Instance-level lock for initialization
        self._last_init_attempt: Optional[float] = None  # Track last initialization attempt
        self._init_backoff_time = 30.0  # Wait 30 seconds between failed init attempts
    
    async def initialize(self):
        # Use instance lock to prevent multiple initializations
        async with self._init_lock:
            if self._initialized:
                return
            
            try:
                db_config = _get_db_config()
                if not db_config or not db_config.get('host') or not db_config.get('database'):
                    raise ValueError(
                        "Database config missing: set DB_HOST, DB_USER, DB_PASSWORD, DB_NAME in .env "
                        "or DATABASE_CONFIG in assets/Configs/bot.json"
                    )
                import logging
                logger = logging.getLogger("DatabasePool")
                logger.info(f"Connecting to database at {db_config.get('host', 'unknown')}:{db_config.get('port', 'unknown')}")
                try:
                    self.pool = await asyncio.wait_for(
                        aiomysql.create_pool(
                            host=db_config['host'],
                            port=int(db_config['port']) if isinstance(db_config.get('port'), str) else db_config.get('port', 3306),
                            user=db_config['user'],
                            password=db_config['password'],
                            db=db_config['database'],
                            autocommit=bool(db_config.get('autocommit', True)),
                            cursorclass=aiomysql.DictCursor,
                            minsize=self.min_size,
                            maxsize=self.max_size,
                            pool_recycle=3600,
                            connect_timeout=5  # Connection timeout in seconds
                        ),
                        timeout=10.0
                    )
                    logger.info("Database pool created successfully")
                    self._initialized = True
                    self._last_init_attempt = None  # Reset on success
                except asyncio.TimeoutError:
                    logger.error("Database connection timed out after 10 seconds")
                    self._initialized = False
                    self.pool = None
                    raise
                except Exception as e:
                    logger.error(f"Failed to create database pool: {e}", exc_info=True)
                    self._initialized = False
                    self.pool = None
                    raise
            except Exception as e:
                import logging
                logger = logging.getLogger("DatabasePool")
                logger.error(f"Failed to initialize database pool: {e}", exc_info=True)
                self._initialized = False
                self.pool = None
                raise
    
    async def close(self):
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()
            self._initialized = False
    
    @asynccontextmanager
    async def acquire(self, timeout: float = 5.0):
        # Wait for initialization if not already initialized
        if not self._initialized:
            import time
            current_time = time.time()
            
            # Check if we should retry initialization (backoff)
            if self._last_init_attempt is not None:
                time_since_last_attempt = current_time - self._last_init_attempt
                if time_since_last_attempt < self._init_backoff_time:
                    raise RuntimeError(
                        f"Database pool initialization failed recently. "
                        f"Retrying in {self._init_backoff_time - time_since_last_attempt:.1f} seconds. "
                        f"Database may be unreachable."
                    )
            
            try:
                self._last_init_attempt = current_time
                # Try to initialize with timeout
                await asyncio.wait_for(self.initialize(), timeout=timeout)
            except asyncio.TimeoutError:
                raise RuntimeError(f"Database pool initialization timed out after {timeout} seconds - database may be unreachable")
            except Exception as e:
                raise RuntimeError(f"Database pool initialization failed: {e}")
        
        if self.pool is None or not self._initialized:
            raise RuntimeError("Database pool is not initialized")
        
        # pool.acquire() returns an async context manager
        cm = self.pool.acquire()
        try:
            # Acquire connection with timeout
            conn = await asyncio.wait_for(cm.__aenter__(), timeout=timeout)
            try:
                yield conn
            finally:
                await cm.__aexit__(None, None, None)
        except asyncio.TimeoutError:
            # Clean up on timeout
            try:
                await cm.__aexit__(None, None, None)
            except:
                pass
            raise RuntimeError(f"Failed to acquire database connection from pool within {timeout} seconds - pool may be exhausted")
        except Exception as e:
            # Clean up on any error
            try:
                await cm.__aexit__(None, None, None)
            except:
                pass
            raise
    
    async def execute(self, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        async with self.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query, params)
                return await cursor.fetchall()
    
    async def execute_many(self, query: str, params_list: List[tuple]) -> int:
        async with self.acquire() as conn:
            async with conn.cursor() as cursor:
                return await cursor.executemany(query, params_list)
    
    async def execute_insert(self, query: str, params: Optional[tuple] = None) -> int:
        async with self.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query, params)
                return cursor.lastrowid
    
    @classmethod
    async def get_instance(cls) -> 'DatabasePool':
        if cls._lock is None:
            cls._lock = asyncio.Lock()
        
        # Create instance if it doesn't exist (thread-safe)
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
                    # Don't wait for initialization here - let it happen lazily
                    # This prevents blocking if the database is slow/unreachable
                    # The initialize() will be called when actually needed via acquire()
        
        return cls._instance

