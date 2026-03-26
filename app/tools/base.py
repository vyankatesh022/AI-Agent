"""Abstract definitions and secure registry for agent tools."""

import logging
import uuid
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class BaseTool(ABC):
    """Abstract base class for all approved agent tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier of the tool."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Detailed description of what the tool accomplishes."""
        pass

    @abstractmethod
    async def execute(
        self,
        user_id: uuid.UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute the tool operation bound to the authenticated user ID.

        Args:
            user_id: Authenticated user UUID extracted from request context.
            **kwargs: Validated operational parameters.

        Returns:
            Dictionary containing execution results.
        """
        pass


class ToolRegistry:
    """Security-focused registry managing allowed tools.

    Guarantees:
    - Only explicitly registered tools can execute.
    - No dynamic code execution (no eval, no exec).
    - No arbitrary shell commands.
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register an approved tool instance."""
        if not tool.name or not isinstance(tool.name, str):
            raise ValueError("Tool name must be a non-empty string.")
        self._tools[tool.name] = tool
        logger.debug("Registered tool: %s", tool.name)

    def get_tool(self, name: str) -> BaseTool | None:
        """Retrieve an approved tool by name, returning None if unapproved."""
        return self._tools.get(name)

    def list_tools(self) -> list[BaseTool]:
        """Return all approved tools."""
        return list(self._tools.values())

    async def execute_tool(
        self,
        tool_name: str,
        user_id: uuid.UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute an approved tool safely under authenticated user authority.

        Raises:
            PermissionError: If the tool is not in the approved registry.
        """
        tool = self.get_tool(tool_name)
        if not tool:
            logger.warning(
                "Attempted execution of unapproved tool '%s' by user '%s'",
                tool_name,
                user_id,
            )
            raise PermissionError(
                f"Tool '{tool_name}' is not an approved tool."
            )

        return await tool.execute(user_id=user_id, **kwargs)
