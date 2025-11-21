"""
Retry handler with exponential backoff for async operations
Provides decorators and utilities for robust error handling
"""

import asyncio
import logging
from functools import wraps
from typing import Callable, Type, Tuple, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    """Configuration for retry behavior"""
    max_attempts: int = 3
    initial_delay: float = 1.0
    backoff_multiplier: float = 2.0
    max_delay: float = 30.0
    exceptions: Tuple[Type[Exception], ...] = (Exception,)
    
    def get_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number"""
        delay = self.initial_delay * (self.backoff_multiplier ** attempt)
        return min(delay, self.max_delay)


def retry_async(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    backoff_multiplier: float = 2.0,
    max_delay: float = 30.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Callable[[Exception, int], None] = None
):
    """
    Decorator for async functions that implements retry logic with exponential backoff.
    
    Args:
        max_attempts: Maximum number of attempts (default: 3)
        initial_delay: Initial delay in seconds (default: 1.0)
        backoff_multiplier: Multiplier for exponential backoff (default: 2.0)
        max_delay: Maximum delay between retries (default: 30.0)
        exceptions: Tuple of exception types to catch (default: all exceptions)
        on_retry: Optional callback function called on each retry
        
    Example:
        @retry_async(max_attempts=5, initial_delay=2.0)
        async def unstable_operation():
            # This will retry up to 5 times with exponential backoff
            await some_flaky_api_call()
    """
    config = RetryConfig(
        max_attempts=max_attempts,
        initial_delay=initial_delay,
        backoff_multiplier=backoff_multiplier,
        max_delay=max_delay,
        exceptions=exceptions
    )
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            
            for attempt in range(config.max_attempts):
                try:
                    return await func(*args, **kwargs)
                    
                except config.exceptions as e:
                    last_exception = e
                    
                    if attempt == config.max_attempts - 1:
                        # Last attempt failed, raise the exception
                        logger.error(
                            f"{func.__name__} failed after {config.max_attempts} attempts: {e}"
                        )
                        raise
                    
                    # Calculate delay for this attempt
                    delay = config.get_delay(attempt)
                    
                    logger.warning(
                        f"{func.__name__} attempt {attempt + 1}/{config.max_attempts} failed: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    
                    # Call retry callback if provided
                    if on_retry:
                        try:
                            on_retry(e, attempt + 1)
                        except Exception as callback_error:
                            logger.error(f"Error in retry callback: {callback_error}")
                    
                    # Wait before retrying
                    await asyncio.sleep(delay)
            
            # Should never reach here, but just in case
            if last_exception:
                raise last_exception
                
        return wrapper
    return decorator


class RetryableOperation:
    """
    Context manager for retryable operations with custom logic.
    Useful when you need more control than the decorator provides.
    
    Example:
        async with RetryableOperation(max_attempts=3) as retry:
            while retry.should_retry():
                try:
                    result = await some_operation()
                    retry.success()
                    return result
                except Exception as e:
                    await retry.handle_error(e)
    """
    
    def __init__(self, config: RetryConfig = None):
        self.config = config or RetryConfig()
        self.attempt = 0
        self.last_error = None
        self._success = False
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Suppress exceptions if we want to handle them manually
        return False
        
    def should_retry(self) -> bool:
        """Check if we should attempt/retry the operation"""
        return self.attempt < self.config.max_attempts and not self._success
        
    async def handle_error(self, error: Exception):
        """Handle an error during the operation"""
        self.last_error = error
        self.attempt += 1
        
        if self.attempt >= self.config.max_attempts:
            logger.error(f"Operation failed after {self.config.max_attempts} attempts: {error}")
            raise error
            
        delay = self.config.get_delay(self.attempt - 1)
        logger.warning(
            f"Operation attempt {self.attempt}/{self.config.max_attempts} failed: {error}. "
            f"Retrying in {delay:.1f}s..."
        )
        await asyncio.sleep(delay)
        
    def success(self):
        """Mark the operation as successful"""
        self._success = True
        if self.attempt > 1:
            logger.info(f"Operation succeeded on attempt {self.attempt}")
