# -*- coding: utf-8 -*-
"""
Comprehensive error handling utility for pharmacy system

Provides standardized error handling, user-friendly error messages,
and error categorization for better error management.
"""

import logging
import traceback
from typing import Optional, Dict, Any
from enum import Enum
from functools import wraps

_logger = logging.getLogger('pharmacy.error')


class ErrorCategory(Enum):
    """Error categories for better error management"""
    VALIDATION = 'validation'  # Data validation errors
    BUSINESS_RULE = 'business_rule'  # Business rule violations
    EXTERNAL_SERVICE = 'external_service'  # External API failures
    DATABASE = 'database'  # Database operation errors
    PERMISSION = 'permission'  # Access control errors
    INTEGRATION = 'integration'  # Integration errors
    SYSTEM = 'system'  # System-level errors
    UNKNOWN = 'unknown'  # Uncategorized errors


class PharmacyError(Exception):
    """
    Base exception class for pharmacy-specific errors
    
    Provides structured error information for better error handling
    and user-friendly error messages.
    """
    
    def __init__(
        self,
        message: str,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        user_message: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None
    ):
        """
        Initialize pharmacy error
        
        Args:
            message: Technical error message
            category: Error category
            user_message: User-friendly error message
            context: Additional context information
            original_exception: Original exception if wrapping
        """
        self.message = message
        self.category = category
        self.user_message = user_message or self._generate_user_message()
        self.context = context or {}
        self.original_exception = original_exception
        super().__init__(self.message)
    
    def _generate_user_message(self) -> str:
        """Generate user-friendly error message from technical message"""
        # Default user-friendly messages by category
        category_messages = {
            ErrorCategory.VALIDATION: "Please check your input and try again.",
            ErrorCategory.BUSINESS_RULE: "This operation is not allowed by business rules.",
            ErrorCategory.EXTERNAL_SERVICE: "External service is temporarily unavailable. Please try again later.",
            ErrorCategory.DATABASE: "A database error occurred. Please contact support.",
            ErrorCategory.PERMISSION: "You don't have permission to perform this action.",
            ErrorCategory.INTEGRATION: "Integration error occurred. Please contact support.",
            ErrorCategory.SYSTEM: "A system error occurred. Please contact support.",
            ErrorCategory.UNKNOWN: "An unexpected error occurred. Please contact support.",
        }
        return category_messages.get(self.category, "An error occurred.")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for API responses"""
        return {
            'error_type': self.__class__.__name__,
            'category': self.category.value,
            'message': self.user_message,
            'technical_message': self.message,
            'context': self.context,
        }


class ValidationError(PharmacyError):
    """Data validation error"""
    def __init__(self, message: str, field: Optional[str] = None, **kwargs):
        context = kwargs.get('context', {})
        if field:
            context['field'] = field
        kwargs['context'] = context
        kwargs['category'] = ErrorCategory.VALIDATION
        super().__init__(message, **kwargs)


class BusinessRuleError(PharmacyError):
    """Business rule violation error"""
    def __init__(self, message: str, rule: Optional[str] = None, **kwargs):
        context = kwargs.get('context', {})
        if rule:
            context['rule'] = rule
        kwargs['context'] = context
        kwargs['category'] = ErrorCategory.BUSINESS_RULE
        super().__init__(message, **kwargs)


class ExternalServiceError(PharmacyError):
    """External service error"""
    def __init__(self, message: str, service: Optional[str] = None, **kwargs):
        context = kwargs.get('context', {})
        if service:
            context['service'] = service
        kwargs['context'] = context
        kwargs['category'] = ErrorCategory.EXTERNAL_SERVICE
        super().__init__(message, **kwargs)


class DatabaseError(PharmacyError):
    """Database operation error"""
    def __init__(self, message: str, operation: Optional[str] = None, **kwargs):
        context = kwargs.get('context', {})
        if operation:
            context['operation'] = operation
        kwargs['context'] = context
        kwargs['category'] = ErrorCategory.DATABASE
        super().__init__(message, **kwargs)


class PermissionError(PharmacyError):
    """Permission error"""
    def __init__(self, message: str, resource: Optional[str] = None, **kwargs):
        context = kwargs.get('context', {})
        if resource:
            context['resource'] = resource
        kwargs['context'] = context
        kwargs['category'] = ErrorCategory.PERMISSION
        super().__init__(message, **kwargs)


def handle_errors(
    default_return=None,
    reraise: bool = True,
    log_error: bool = True,
    error_category: ErrorCategory = ErrorCategory.UNKNOWN
):
    """
    Decorator for standardized error handling
    
    Args:
        default_return: Value to return on error (if not reraising)
        reraise: Whether to re-raise the exception
        log_error: Whether to log the error
        error_category: Default error category for unhandled exceptions
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except PharmacyError as e:
                # Already a pharmacy error, just log and handle
                if log_error:
                    _logger.error(
                        f"Pharmacy error in {func.__name__}: {e.message}",
                        extra={'extra_data': {
                            'function': func.__name__,
                            'category': e.category.value,
                            'context': e.context,
                        }},
                        exc_info=True
                    )
                if reraise:
                    raise
                return default_return
            except Exception as e:
                # Convert to pharmacy error
                error = PharmacyError(
                    message=str(e),
                    category=error_category,
                    original_exception=e,
                    context={'function': func.__name__}
                )
                
                if log_error:
                    _logger.error(
                        f"Unexpected error in {func.__name__}: {str(e)}",
                        extra={'extra_data': {
                            'function': func.__name__,
                            'category': error_category.value,
                            'traceback': traceback.format_exc(),
                        }},
                        exc_info=True
                    )
                
                if reraise:
                    raise error
                return default_return
        
        return wrapper
    return decorator


def safe_execute(
    func: callable,
    *args,
    default_return=None,
    error_category: ErrorCategory = ErrorCategory.UNKNOWN,
    **kwargs
) -> Any:
    """
    Safely execute a function with error handling
    
    Args:
        func: Function to execute
        *args: Function arguments
        default_return: Value to return on error
        error_category: Error category for exceptions
        **kwargs: Function keyword arguments
        
    Returns:
        Function result or default_return on error
    """
    try:
        return func(*args, **kwargs)
    except PharmacyError as e:
        _logger.warning(
            f"Pharmacy error in {func.__name__}: {e.message}",
            extra={'extra_data': {
                'function': func.__name__,
                'category': e.category.value,
            }}
        )
        return default_return
    except Exception as e:
        _logger.error(
            f"Unexpected error in {func.__name__}: {str(e)}",
            extra={'extra_data': {
                'function': func.__name__,
                'category': error_category.value,
            }},
            exc_info=True
        )
        return default_return


def get_user_friendly_error(error: Exception) -> str:
    """
    Get user-friendly error message from exception
    
    Args:
        error: Exception to convert
        
    Returns:
        User-friendly error message
    """
    if isinstance(error, PharmacyError):
        return error.user_message
    
    # Handle common Odoo exceptions
    from odoo.exceptions import UserError, ValidationError as OdooValidationError
    
    if isinstance(error, UserError):
        return str(error.args[0]) if error.args else "An error occurred."
    
    if isinstance(error, OdooValidationError):
        return str(error.args[0]) if error.args else "Invalid data provided."
    
    # Default message
    return "An unexpected error occurred. Please contact support if the problem persists."


def log_error_context(
    error: Exception,
    context: Optional[Dict[str, Any]] = None,
    level: str = 'ERROR'
):
    """
    Log error with context information
    
    Args:
        error: Exception to log
        context: Additional context information
        level: Log level (ERROR, WARNING, INFO)
    """
    log_func = getattr(_logger, level.lower(), _logger.error)
    
    extra_data = {
        'error_type': type(error).__name__,
        'error_message': str(error),
    }
    
    if isinstance(error, PharmacyError):
        extra_data.update({
            'category': error.category.value,
            'context': error.context,
        })
    
    if context:
        extra_data.update(context)
    
    log_func(
        f"Error logged: {type(error).__name__}",
        extra={'extra_data': extra_data},
        exc_info=True
    )
