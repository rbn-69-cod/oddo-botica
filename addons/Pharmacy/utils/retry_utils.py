# -*- coding: utf-8 -*-
"""
Retry utility for external API calls with exponential backoff

Provides retry logic with exponential backoff, circuit breaker pattern,
and dead letter queue for failed operations.
"""

import time
import logging
from functools import wraps
from typing import Callable, Optional, Type, Tuple, Any
from enum import Enum

_logger = logging.getLogger('pharmacy.retry')


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = 'closed'  # Normal operation
    OPEN = 'open'      # Circuit is open, blocking calls
    HALF_OPEN = 'half_open'  # Testing if service is recovered


class CircuitBreaker:
    """
    Circuit breaker pattern implementation for external service calls
    
    Prevents cascading failures by blocking calls to failing services
    after a threshold of consecutive failures.
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: Tuple[Type[Exception], ...] = (Exception,)
    ):
        """
        Initialize circuit breaker
        
        Args:
            failure_threshold: Number of consecutive failures before opening circuit
            recovery_timeout: Seconds to wait before attempting recovery
            expected_exception: Exception types that count as failures
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection
        
        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
            
        Raises:
            Exception: If circuit is open or function fails
        """
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                _logger.info("Circuit breaker attempting reset")
            else:
                raise Exception(f"Circuit breaker is OPEN for {func.__name__}")
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt recovery"""
        if self.last_failure_time is None:
            return True
        return (time.time() - self.last_failure_time) >= self.recovery_timeout
    
    def _on_success(self):
        """Handle successful call"""
        self.failure_count = 0
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            _logger.info("Circuit breaker reset to CLOSED")
    
    def _on_failure(self):
        """Handle failed call"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            _logger.warning(
                f"Circuit breaker opened after {self.failure_count} failures"
            )


def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 10.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    expected_exception: Tuple[Type[Exception], ...] = (Exception,)
):
    """
    Decorator for retrying function calls with exponential backoff
    
    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        exponential_base: Base for exponential backoff calculation
        jitter: Add random jitter to delay to prevent thundering herd
        expected_exception: Exception types that trigger retry
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            delay = initial_delay
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except expected_exception as e:
                    last_exception = e
                    
                    if attempt == max_retries:
                        _logger.error(
                            f"Function {func.__name__} failed after {max_retries} retries",
                            extra={'extra_data': {
                                'function': func.__name__,
                                'attempts': attempt + 1,
                                'final_error': str(e)
                            }}
                        )
                        raise
                    
                    # Calculate delay with exponential backoff
                    if jitter:
                        import random
                        delay = min(
                            max_delay,
                            (initial_delay * (exponential_base ** attempt)) + random.uniform(0, 1)
                        )
                    else:
                        delay = min(max_delay, initial_delay * (exponential_base ** attempt))
                    
                    _logger.warning(
                        f"Retry {attempt + 1}/{max_retries} for {func.__name__} after {delay:.2f}s delay",
                        extra={'extra_data': {
                            'function': func.__name__,
                            'attempt': attempt + 1,
                            'delay': delay,
                            'error': str(e)
                        }}
                    )
                    
                    time.sleep(delay)
            
            # This should never be reached
            raise last_exception
        
        return wrapper
    return decorator


class DeadLetterQueue:
    """
    Dead letter queue for failed operations
    
    Stores failed operations for later processing and analysis.
    """
    
    def __init__(self, max_size: int = 1000):
        """
        Initialize dead letter queue
        
        Args:
            max_size: Maximum number of items to store
        """
        self.max_size = max_size
        self._queue = []
    
    def add(
        self,
        operation: str,
        args: tuple,
        kwargs: dict,
        exception: Exception,
        timestamp: Optional[float] = None
    ):
        """
        Add failed operation to queue
        
        Args:
            operation: Operation name/function
            args: Function arguments
            kwargs: Function keyword arguments
            exception: Exception that occurred
            timestamp: Optional timestamp (defaults to current time)
        """
        if timestamp is None:
            timestamp = time.time()
        
        item = {
            'operation': operation,
            'args': str(args)[:500],  # Truncate long args
            'kwargs': str(kwargs)[:500],
            'exception_type': type(exception).__name__,
            'exception_message': str(exception),
            'timestamp': timestamp,
        }
        
        self._queue.append(item)
        
        # Enforce max size
        if len(self._queue) > self.max_size:
            self._queue.pop(0)
        
        _logger.warning(
            f"Added failed operation to dead letter queue: {operation}",
            extra={'extra_data': item}
        )
    
    def get_all(self) -> list:
        """Get all items in queue"""
        return self._queue.copy()
    
    def clear(self):
        """Clear the queue"""
        self._queue.clear()
        _logger.info("Dead letter queue cleared")
    
    def size(self) -> int:
        """Get current queue size"""
        return len(self._queue)


# Global dead letter queue instance
global_dlq = DeadLetterQueue()


def with_retry_and_circuit_breaker(
    max_retries: int = 3,
    circuit_breaker: Optional[CircuitBreaker] = None,
    use_dlq: bool = True
):
    """
    Combined decorator for retry logic and circuit breaker
    
    Args:
        max_retries: Maximum retry attempts
        circuit_breaker: Optional circuit breaker instance
        use_dlq: Whether to use dead letter queue for final failures
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        @retry_with_backoff(max_retries=max_retries)
        def wrapper(*args, **kwargs) -> Any:
            if circuit_breaker:
                return circuit_breaker.call(func, *args, **kwargs)
            return func(*args, **kwargs)
        
        # Add dead letter queue handling
        if use_dlq:
            original_wrapper = wrapper
            
            @wraps(wrapper)
            def dlq_wrapper(*args, **kwargs) -> Any:
                try:
                    return original_wrapper(*args, **kwargs)
                except Exception as e:
                    global_dlq.add(
                        operation=func.__name__,
                        args=args,
                        kwargs=kwargs,
                        exception=e
                    )
                    raise
            
            return dlq_wrapper
        
        return wrapper
    return decorator
