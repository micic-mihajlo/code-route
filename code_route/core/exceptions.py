"""Custom exceptions for Code Route."""

from typing import Any, Dict, Optional


class CodeRouteError(Exception):
    """Base exception for all Code Route errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ProviderError(CodeRouteError):
    """Error from an LLM provider."""

    def __init__(
        self,
        message: str,
        provider: str,
        status_code: Optional[int] = None,
        retryable: bool = False,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, details)
        self.provider = provider
        self.status_code = status_code
        self.retryable = retryable


class RateLimitError(ProviderError):
    """Rate limit exceeded."""

    def __init__(
        self,
        message: str,
        provider: str,
        retry_after: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, provider, status_code=429, retryable=True, details=details)
        self.retry_after = retry_after


class AuthenticationError(ProviderError):
    """Authentication failed."""

    def __init__(self, message: str, provider: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, provider, status_code=401, retryable=False, details=details)


class ToolError(CodeRouteError):
    """Error during tool execution."""

    def __init__(
        self,
        message: str,
        tool_name: str,
        recoverable: bool = True,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, details)
        self.tool_name = tool_name
        self.recoverable = recoverable


class ToolNotFoundError(ToolError):
    """Tool not found in registry."""

    def __init__(self, tool_name: str):
        super().__init__(f"Tool not found: {tool_name}", tool_name, recoverable=False)


class ToolValidationError(ToolError):
    """Tool input validation failed."""

    def __init__(self, tool_name: str, validation_errors: Dict[str, str]):
        message = f"Validation failed for {tool_name}: {validation_errors}"
        super().__init__(message, tool_name, recoverable=True, details={"errors": validation_errors})
        self.validation_errors = validation_errors


class AgentError(CodeRouteError):
    """Error during agent execution."""

    def __init__(
        self,
        message: str,
        agent_type: str,
        task_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, details)
        self.agent_type = agent_type
        self.task_id = task_id


class MemoryError(CodeRouteError):
    """Error with memory/persistence operations."""

    def __init__(self, message: str, operation: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, details)
        self.operation = operation


class ConfigError(CodeRouteError):
    """Configuration error."""

    def __init__(self, message: str, config_key: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, details)
        self.config_key = config_key
