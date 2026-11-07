"""Shared tool call validation for orchestrator and multi-step evaluation."""

from __future__ import annotations

import logging
from typing import Any

import jsonschema

from syssathi.host.mcp_client import ALLOWED_EVON_TOOLS

logger = logging.getLogger(__name__)


def validate_tool_call(
    tool_name: str,
    tool_args: dict[str, Any],
    tool_schema_map: dict[str, Any],
) -> tuple[bool, str | None]:
    """Validate a tool call against the allowlist and JSON schema.
    
    Returns (is_valid, error_message).
    """
    if tool_name not in ALLOWED_EVON_TOOLS:
        err = f"Disallowed tool '{tool_name}' (allowed: {sorted(ALLOWED_EVON_TOOLS)})"
        logger.warning(err)
        return False, err

    schema = tool_schema_map.get(tool_name)
    if schema:
        try:
            jsonschema.validate(tool_args, schema)
        except jsonschema.ValidationError as e:
            err = f"Schema validation error on {tool_name}: {e.message}"
            logger.warning(err)
            return False, err

    return True, None
