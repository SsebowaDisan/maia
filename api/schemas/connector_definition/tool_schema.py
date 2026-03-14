"""ToolSchema — describes a single callable tool exposed by a connector.

Responsibility: single pydantic schema for a connector tool definition.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ToolParameterType(str, Enum):
    string = "string"
    integer = "integer"
    number = "number"
    boolean = "boolean"
    array = "array"
    object = "object"


class ToolParameter(BaseModel):
    """One parameter in a tool's input schema."""

    name: str
    type: ToolParameterType
    description: str = ""
    required: bool = True
    default: Any = None

    # For string parameters: allowed values (turns this into an enum).
    enum: list[str] | None = None

    # For array parameters: the type of each item.
    items_type: ToolParameterType | None = None

    # JSON Schema for object parameters.
    properties: dict[str, Any] | None = None


class ToolActionClass(str, Enum):
    """Broad action classification used by the gate engine and audit log."""

    read = "read"       # Non-mutating data read (safe to auto-approve).
    draft = "draft"     # Creates a local draft only (no external side effects).
    execute = "execute" # Mutates external state — typically requires a gate.


class ToolSchema(BaseModel):
    """Declaration of a single tool exposed by a connector."""

    # Stable identifier for this tool within the connector, e.g. "send_email".
    id: str = Field(..., min_length=1, max_length=64)

    # Human-readable name shown in the agent builder UI.
    name: str

    # Description injected into the agent's system prompt for tool selection.
    description: str

    # Input parameters; maps to the LLM function-calling schema.
    parameters: list[ToolParameter] = Field(default_factory=list)

    # Broad action class — informs gate engine defaults and audit logging.
    action_class: ToolActionClass = ToolActionClass.read

    # Whether the platform exposes this tool in the marketplace tool catalog.
    is_public: bool = True

    # Approximate tokens consumed per call (used for billing estimates).
    estimated_tokens: int = 0

    def to_llm_function_spec(self) -> dict[str, Any]:
        """Render this tool as an OpenAI-compatible function spec dict."""
        properties: dict[str, Any] = {}
        required_names: list[str] = []

        for param in self.parameters:
            prop: dict[str, Any] = {
                "type": param.type.value,
                "description": param.description,
            }
            if param.enum:
                prop["enum"] = param.enum
            if param.items_type and param.type == ToolParameterType.array:
                prop["items"] = {"type": param.items_type.value}
            if param.properties and param.type == ToolParameterType.object:
                prop["properties"] = param.properties
            if param.default is not None:
                prop["default"] = param.default

            properties[param.name] = prop
            if param.required:
                required_names.append(param.name)

        return {
            "name": self.id,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required_names,
            },
        }
