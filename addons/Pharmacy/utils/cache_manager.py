# -*- coding: utf-8 -*-
"""
Redis Cache Manager for Pharmacy System

Provides caching for frequently accessed data to improve performance.
"""

import json
import logging
from typing import Optional, Any, Dict, List
from datetime import timedelta

_logger = logging.getLogger('pharmacy.cache')


class CacheManager:
    """Redis-based cache manager for pharmacy system"""
    
    def __init__(self, redis_client=None):
        """
        Initialize cache manager
        
        Args:
            redis_client: Redis client instance (if None, will try to connect)
        """
        self.redis = redis_client
        self.enabled = False
        
        if self.redis is None:
            try:
                import redis
                self.redis = redis.Redis(
                    host='localhost',
                    port=6379,
                    db=0,
                    decode_responses=True,
                    socket_timeout=5,
                    socket_connect_timeout=5
                )
                # Test connection
                self.redis.ping()
                self.enabled = True
                _logger.info("Redis cache enabled")
            except Exception as e:
                _logger.warning(f"Redis not available: {str(e)}")
                self.enabled = False
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found
        """
        if not self.enabled:
            return None
        
        try:
            value = self.redis.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            _logger.error(f"Cache get error for key {key}: {str(e)}")
            return None
    
    def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """
        Set value in cache
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (default: 1 hour)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.enabled:
            return False
        
        try:
            serialized = json.dumps(value)
            self.redis.setex(key, ttl, serialized)
            return True
        except Exception as e:
            _logger.error(f"Cache set error for key {key}: {str(e)}")
            return False
    
    def delete(self, key: str) -> bool:
        """
        Delete value from cache
        
        Args:
            key: Cache key
            
        Returns:
            True if successful, False otherwise
        """
        if not self.enabled:
            return False
        
        try:
            self.redis.delete(key)
            return True
        except Exception as e:
            _logger.error(f"Cache delete error for key {key}: {str(e)}")
            return False
    
    def delete_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching pattern
        
        Args:
            pattern: Key pattern (e.g., "patient:*")
            
        Returns:
            Number of keys deleted
        """
        if not self.enabled:
            return 0
        
        try:
            keys = self.redis.keys(pattern)
            if keys:
                return self.redis.delete(*keys)
            return 0
        except Exception as e:
            _logger.error(f"Cache delete pattern error for {pattern}: {str(e)}")
            return 0
    
    def invalidate_model(self, model_name: str, record_id: Optional[int] = None):
        """
        Invalidate cache for a model
        
        Args:
            model_name: Model name (e.g., 'pharmacy.patient')
            record_id: Optional record ID to invalidate specific record
        """
        if record_id:
            pattern = f"{model_name}:{record_id}:*"
        else:
            pattern = f"{model_name}:*"
        
        deleted = self.delete_pattern(pattern)
        if deleted > 0:
            _logger.info(f"Invalidated {deleted} cache entries for {pattern}")
    
    def get_or_compute(self, key: str, compute_func, ttl: int = 3600) -> Any:
        """
        Get value from cache or compute and cache it
        
        Args:
            key: Cache key
            compute_func: Function to compute value if not cached
            ttl: Time to live in seconds
            
        Returns:
            Cached or computed value
        """
        value = self.get(key)
        if value is not None:
            return value
        
        # Compute value
        value = compute_func()
        
        # Cache it
        self.set(key, value, ttl)
        
        return value
    
    def clear_all(self) -> bool:
        """
        Clear all cached data
        
        Returns:
            True if successful, False otherwise
        """
        if not self.enabled:
            return False
        
        try:
            self.redis.flushdb()
            _logger.info("Cache cleared")
            return True
        except Exception as e:
            _logger.error(f"Cache clear error: {str(e)}")
            return False


# Global cache manager instance
cache_manager = CacheManager()


def cached(ttl: int = 3600, key_prefix: str = None):
    """
    Decorator for caching function results
    
    Args:
        ttl: Time to live in seconds
        key_prefix: Prefix for cache key (defaults to function name)
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            if not cache_manager.enabled:
                return func(*args, **kwargs)
            
            # Generate cache key
            if key_prefix:
                cache_key = f"{key_prefix}:{str(args)}:{str(kwargs)}"
            else:
                cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            
            # Try to get from cache
            cached_value = cache_manager.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # Compute and cache
            result = func(*args, **kwargs)
            cache_manager.set(cache_key, result, ttl)
            
            return result
        return wrapper
    return decorator


def invalidate_cache_on_change(model_name: str):
    """
    Decorator to invalidate cache when model changes
    
    Args:
        model_name: Model name to invalidate
    """
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            result = func(self, *args, **kwargs)
            
            # Invalidate cache for this model
            if hasattr(self, 'id') and self.id:
                cache_manager.invalidate_model(model_name, self.id)
            else:
                cache_manager.invalidate_model(model_name)
            
            return result
        return wrapper
    return decorator
