"""Tests for tool JSON schemas."""

from infrastructure.local_execution.tools import TOOL_REGISTRY
from infrastructure.local_execution.tools.tool_schemas import TOOL_SCHEMAS, get_openai_tools


class TestToolSchemas:
    def test_all_registry_tools_have_schemas(self):
        """Every tool in TOOL_REGISTRY should have a corresponding schema."""
        for tool_name in TOOL_REGISTRY:
            assert tool_name in TOOL_SCHEMAS, f"Missing schema for tool: {tool_name}"

    def test_all_schemas_have_name_and_description(self):
        for name, schema in TOOL_SCHEMAS.items():
            assert schema.name == name
            assert len(schema.description) > 0, f"Schema {name} has empty description"

    def test_get_openai_tools_all(self):
        tools = get_openai_tools()
        assert len(tools) == len(TOOL_SCHEMAS)
        for tool in tools:
            assert tool["type"] == "function"
            assert "name" in tool["function"]
            assert "description" in tool["function"]
            assert "parameters" in tool["function"]

    def test_get_openai_tools_filtered(self):
        tools = get_openai_tools(["web_search", "web_fetch"])
        assert len(tools) == 2
        names = {t["function"]["name"] for t in tools}
        assert names == {"web_search", "web_fetch"}

    def test_get_openai_tools_missing_name_skipped(self):
        tools = get_openai_tools(["web_search", "nonexistent_tool"])
        assert len(tools) == 1
        assert tools[0]["function"]["name"] == "web_search"

    def test_web_search_schema_has_required_query(self):
        schema = TOOL_SCHEMAS["web_search"]
        assert "query" in schema.required
        assert "query" in schema.properties

    def test_web_fetch_schema_has_required_url(self):
        schema = TOOL_SCHEMAS["web_fetch"]
        assert "url" in schema.required

    def test_openai_tool_format(self):
        tool = TOOL_SCHEMAS["shell_exec"].to_openai_tool()
        assert tool["type"] == "function"
        params = tool["function"]["parameters"]
        assert params["type"] == "object"
        assert "cmd" in params["properties"]
        assert "cmd" in params["required"]
