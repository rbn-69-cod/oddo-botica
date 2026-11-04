# -*- coding: utf-8 -*-
"""
Structured logging utility for pharmacy system

Provides JSON-formatted structured logging with correlation IDs
for better log aggregation and analysis in production environments.
"""

import logging
import json
import time
import uuid
from contextvars import ContextVar
from functools import wraps
from typing import Optional, Dict, Any

# Context variable for correlation ID (tracks request flow across async operations)
correlation_id: ContextVar[Optional[str]] = ContextVar('correlation_id', default=None)


class PharmacyJSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging"""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON"""
        
        # Get correlation ID from context
        corr_id = correlation_id.get()
        
        # Build structured log entry
        log_entry = {
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S.%fZ', time.gmtime(record.created)),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
            'correlation_id': corr_id,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        
        # Add extra fields if present
        if hasattr(record, 'extra_data'):
            log_entry.update(record.extra_data)
        
        return json.dumps(log_entry)


def setup_structured_logging(log_level: str = 'INFO', log_file: Optional[str] = None):
    """
    Configure structured logging for the pharmacy module
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional log file path
    """
    # Create pharmacy logger
    logger = logging.getLogger('pharmacy')
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Remove existing handlers
    logger.handlers.clear()
    
    # Create JSON formatter
    formatter = PharmacyJSONFormatter()
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


def log_with_context(extra_data: Optional[Dict[str, Any]] = None):
    """
    Decorator to add extra context to log messages
    
    Args:
        extra_data: Dictionary of extra data to include in log entries
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate correlation ID if not set
            if correlation_id.get() is None:
                correlation_id.set(str(uuid.uuid4()))
            
            # Log function entry
            logger = logging.getLogger('pharmacy')
            logger.info(
                f"Entering {func.__name__}",
                extra={'extra_data': {
                    'function': func.__name__,
                    'args': str(args)[:200],  # Truncate long args
                    'kwargs': str(kwargs)[:200],
                    **(extra_data or {})
                }}
            )
            
            try:
                result = func(*args, **kwargs)
                
                # Log function exit
                logger.info(
                    f"Exiting {func.__name__}",
                    extra={'extra_data': {
                        'function': func.__name__,
                        'status': 'success',
                        **(extra_data or {})
                    }}
                )
                
                return result
                
            except Exception as e:
                # Log function error
                logger.error(
                    f"Error in {func.__name__}",
                    extra={'extra_data': {
                        'function': func.__name__,
                        'status': 'error',
                        'error_type': type(e).__name__,
                        'error_message': str(e),
                        **(extra_data or {})
                    }},
                    exc_info=True
                )
                raise
        
        return wrapper
    return decorator


def get_logger(name: str) -> logging.Logger:
    """
    Get a structured logger for a specific module
    
    Args:
        name: Logger name (typically __name__)
    
    Returns:
        Configured logger instance
    """
    return logging.getLogger(f'pharmacy.{name}')


def set_correlation_id(corr_id: str):
    """
    Set correlation ID for current context
    
    Args:
        corr_id: Correlation ID string
    """
    correlation_id.set(corr_id)


def get_correlation_id() -> Optional[str]:
    """
    Get current correlation ID
    
    Returns:
        Correlation ID or None
    """
    return correlation_id.get()


# Initialize structured logging on module import
setup_structured_logging(log_level='INFO')
