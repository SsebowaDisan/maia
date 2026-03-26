from __future__ import annotations

from api.sdk.connector_sdk import ConnectorBase, tool
from api.schemas.connector_definition.tool_schema import ToolActionClass, ToolParameterType


class DemoConnector(ConnectorBase):
    connector_id = "demo"
    display_name = "Demo Connector"
    description = "Demo tools for schema generation tests."

    @tool(description="Create a contact.", read_only=False)
    def create_contact(
        self,
        first_name: str,
        last_name: str,
        email: str,
        age: int | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, str] | None = None,
        subscribed: bool = False,
    ) -> dict:
        return {}

    @tool(
        description="Send an email.",
        params={
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email"},
                "subject": {"type": "string", "description": "Email subject"},
                "body": {"type": "string", "description": "Email body"},
                "tags": {"type": "array", "items": {"type": "string"}, "required": False},
                "options": {
                    "type": "object",
                    "description": "Send options",
                    "properties": {
                        "track_opens": {"type": "boolean"},
                        "priority": {"type": "string", "enum": ["low", "normal", "high"]},
                    },
                    "required": False,
                },
            },
            "required": ["to", "subject", "body"],
        },
        read_only=False,
    )
    def send_email(self, **_: object) -> dict:
        return {}


def test_build_definition_infers_multiple_named_parameters() -> None:
    definition = DemoConnector().build_definition()

    assert definition.name == "Demo Connector"

    tool = definition.get_tool("demo.create_contact")
    assert tool is not None
    assert tool.action_class == ToolActionClass.execute

    params = {param.name: param for param in tool.parameters}
    assert set(params) == {
        "first_name",
        "last_name",
        "email",
        "age",
        "tags",
        "metadata",
        "subscribed",
    }
    assert params["first_name"].type == ToolParameterType.string
    assert params["age"].type == ToolParameterType.integer
    assert params["tags"].type == ToolParameterType.array
    assert params["tags"].items_type == ToolParameterType.string
    assert params["metadata"].type == ToolParameterType.object
    assert params["subscribed"].type == ToolParameterType.boolean
    assert params["first_name"].required is True
    assert params["age"].required is False

    llm_spec = tool.to_llm_function_spec()
    assert llm_spec["parameters"]["type"] == "object"
    assert set(llm_spec["parameters"]["properties"]) >= {"first_name", "email", "tags", "metadata"}
    assert set(llm_spec["parameters"]["required"]) == {"first_name", "last_name", "email"}


def test_build_definition_accepts_explicit_object_schema_with_multiple_parameters() -> None:
    definition = DemoConnector().build_definition()

    tool = definition.get_tool("demo.send_email")
    assert tool is not None
    assert tool.action_class == ToolActionClass.execute

    params = {param.name: param for param in tool.parameters}
    assert params["to"].type == ToolParameterType.string
    assert params["subject"].type == ToolParameterType.string
    assert params["body"].type == ToolParameterType.string
    assert params["tags"].type == ToolParameterType.array
    assert params["tags"].items_type == ToolParameterType.string
    assert params["options"].type == ToolParameterType.object
    assert params["options"].required is False
    assert params["options"].properties == {
        "track_opens": {"type": "boolean"},
        "priority": {"type": "string", "enum": ["low", "normal", "high"]},
    }

    llm_spec = tool.to_llm_function_spec()
    assert set(llm_spec["parameters"]["required"]) == {"to", "subject", "body"}
    assert llm_spec["parameters"]["properties"]["options"]["type"] == "object"
    assert llm_spec["parameters"]["properties"]["tags"]["items"]["type"] == "string"
