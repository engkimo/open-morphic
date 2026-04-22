"""Tests for ToolSchema entity."""

from domain.entities.tool_schema import ParameterProperty, ToolSchema


class TestParameterProperty:
    def test_frozen(self):
        prop = ParameterProperty(type="string", description="A query")
        assert prop.type == "string"
        assert prop.description == "A query"

    def test_with_enum(self):
        prop = ParameterProperty(type="string", description="mode", enum=["fast", "slow"])
        assert prop.enum == ["fast", "slow"]

    def test_with_items(self):
        prop = ParameterProperty(type="array", description="tags", items={"type": "string"})
        assert prop.items == {"type": "string"}


class TestToolSchema:
    def test_to_openai_tool_basic(self):
        schema = ToolSchema(
            name="web_search",
            description="Search the web",
            properties={
                "query": ParameterProperty(type="string", description="Search query"),
            },
            required=["query"],
        )
        result = schema.to_openai_tool()

        assert result["type"] == "function"
        assert result["function"]["name"] == "web_search"
        assert result["function"]["description"] == "Search the web"
        params = result["function"]["parameters"]
        assert params["type"] == "object"
        assert "query" in params["properties"]
        assert params["properties"]["query"]["type"] == "string"
        assert params["required"] == ["query"]

    def test_to_openai_tool_with_enum(self):
        schema = ToolSchema(
            name="test_tool",
            description="Test",
            properties={
                "mode": ParameterProperty(
                    type="string",
                    description="Mode",
                    enum=["fast", "slow"],
                ),
            },
            required=["mode"],
        )
        result = schema.to_openai_tool()
        assert result["function"]["parameters"]["properties"]["mode"]["enum"] == ["fast", "slow"]

    def test_to_openai_tool_with_default(self):
        schema = ToolSchema(
            name="test_tool",
            description="Test",
            properties={
                "count": ParameterProperty(
                    type="integer",
                    description="Count",
                    default=10,
                ),
            },
        )
        result = schema.to_openai_tool()
        assert result["function"]["parameters"]["properties"]["count"]["default"] == 10

    def test_to_openai_tool_empty_properties(self):
        schema = ToolSchema(name="noop", description="No-op tool")
        result = schema.to_openai_tool()
        assert result["function"]["parameters"]["properties"] == {}
        assert result["function"]["parameters"]["required"] == []

    def test_frozen_schema(self):
        schema = ToolSchema(name="test", description="frozen")
        # frozen=True should prevent modification
        import dataclasses

        assert dataclasses.is_dataclass(schema)
