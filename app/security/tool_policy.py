"""Tool authorization policy enforcer and execution bounds checker."""

import logging
import uuid
from typing import Any

from app.config import get_settings
from app.security.errors import ToolAuthorizationError

logger = logging.getLogger(__name__)


class ToolPolicyEnforcer:
    """Enforces authorization, tenant-binding, and loop limits on agent tool calls.

    Guarantees:
    1. Allowlist enforcement: Only explicitly approved tools can be executed.
    2. Tenant-context binding: The user_id is authoritatively bound to the authenticated
       caller context; model-supplied user IDs are strictly ignored/overwritten.
    3. Loop & iteration bounding: Tool executions per request are strictly capped
       by MAX_TOOL_CALLS_PER_REQUEST (default: 5) to prevent recursive billing exhaustion.
    4. Prohibits dangerous operations (eval, exec, file system traversal, shell commands).
    """

    ALLOWED_TOOLS: set[str] = {"safe_database"}
    ALLOWED_OPERATIONS: dict[str, set[str]] = {
        "safe_database": {"get_current_user_profile", "get_user_conversations"},
    }

    def __init__(self, max_tool_calls: int | None = None) -> None:
        settings = get_settings()
        self.max_tool_calls = (
            max_tool_calls
            if max_tool_calls is not None
            else getattr(settings, "MAX_TOOL_CALLS_PER_REQUEST", 5)
        )
        self._call_count: int = 0

    @property
    def call_count(self) -> int:
        return self._call_count

    def validate_and_authorize(
        self,
        tool_name: str,
        user_id: uuid.UUID,
        operation: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Authorize and bind arguments for a tool call.

        Returns:
            Sanitized and authorized kwargs dictionary.

        Raises:
            ToolAuthorizationError: On policy violations or loop bounds exceeded.
        """
        # 1. Enforce execution loop bounds
        if self._call_count >= self.max_tool_calls:
            logger.error(
                "Tool call rejected: exceeded maximum allowed calls (%d) for user %s",
                self.max_tool_calls,
                user_id,
            )
            raise ToolAuthorizationError(
                f"Maximum allowed tool calls ({self.max_tool_calls}) exceeded for this request."
            )

        # 2. Enforce tool allowlist
        if tool_name not in self.ALLOWED_TOOLS:
            logger.error(
                "Unauthorized tool invocation attempt: tool='%s' user='%s'",
                tool_name,
                user_id,
            )
            raise ToolAuthorizationError(
                f"Tool '{tool_name}' is not authorized for execution."
            )

        # 3. Enforce operation allowlist if applicable
        if tool_name in self.ALLOWED_OPERATIONS:
            allowed_ops = self.ALLOWED_OPERATIONS[tool_name]
            if operation and operation not in allowed_ops:
                logger.error(
                    "Unauthorized operation '%s' for tool '%s' user '%s'",
                    operation,
                    tool_name,
                    user_id,
                )
                raise ToolAuthorizationError(
                    f"Operation '{operation}' is not permitted for tool '{tool_name}'."
                )

        self._call_count += 1

        # 4. Bind authorized user_id securely, discarding any model-provided user_id
        safe_kwargs = dict(kwargs)
        safe_kwargs["user_id"] = user_id
        if operation:
            safe_kwargs["operation"] = operation

        return safe_kwargs

    def reset(self) -> None:
        """Reset execution count counter."""
        self._call_count = 0
