from typing import Any, Optional, Dict
from datetime import datetime, timedelta
import asyncio
from threading import Lock


class CacheEntry:
    def __init__(self, value: Any, ttl: Optional[float] = None):
        self.value = value
        self.created_at = datetime.now()
        self.ttl = ttl
    
    def is_expired(self) -> bool:
        if self.ttl is None:
            return False
        return (datetime.now() - self.created_at).total_seconds() > self.ttl


class CacheManager:
    _instance: Optional['CacheManager'] = None
    _lock = Lock()
    
    def __init__(self):
        self._cache: Dict[str, CacheEntry] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
    
    def get(self, key: str) -> Optional[Any]:
        entry = self._cache.get(key)
        if entry is None:
            return None
        
        if entry.is_expired():
            del self._cache[key]
            return None
        
        return entry.value
    
    def set(self, key: str, value: Any, ttl: Optional[float] = None):
        self._cache[key] = CacheEntry(value, ttl)
    
    def delete(self, key: str):
        if key in self._cache:
            del self._cache[key]
    
    def clear(self):
        self._cache.clear()
    
    def _cleanup_expired(self):
        expired_keys = [k for k, v in self._cache.items() if v.is_expired()]
        for key in expired_keys:
            del self._cache[key]
    
    async def start_cleanup_task(self, interval: float = 60.0):
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop(interval))
    
    async def _cleanup_loop(self, interval: float):
        while True:
            await asyncio.sleep(interval)
            self._cleanup_expired()
    
    @classmethod
    def get_instance(cls) -> 'CacheManager':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

