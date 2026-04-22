"""Tests for ArtifactExtractor — smart artifact extraction from engine output.

Sprint 13.4b: Artifact Runtime Extraction.
"""

from domain.services.artifact_extractor import (
    ArtifactExtractor,
    ExtractedContent,
)

# ── Extract ──


class TestExtract:
    def test_empty_text(self) -> None:
        result = ArtifactExtractor.extract("")
        assert result == ExtractedContent()

    def test_none_like_empty(self) -> None:
        """extract() should handle empty string gracefully."""
        r = ArtifactExtractor.extract("")
        assert r.code_blocks == []
        assert r.urls == []
        assert r.json_blocks == []
        assert r.full_text == ""

    def test_extract_single_code_block(self) -> None:
        text = "Here is the code:\n```python\nprint('hello')\n```\nDone."
        r = ArtifactExtractor.extract(text)
        assert len(r.code_blocks) == 1
        assert r.code_blocks[0] == ("python", "print('hello')")

    def test_extract_code_block_no_language(self) -> None:
        text = "Result:\n```\nx = 42\n```"
        r = ArtifactExtractor.extract(text)
        assert len(r.code_blocks) == 1
        assert r.code_blocks[0] == ("", "x = 42")

    def test_extract_multiple_code_blocks(self) -> None:
        text = "```python\ndef foo(): pass\n```\nAnd also:\n```bash\necho hi\n```"
        r = ArtifactExtractor.extract(text)
        assert len(r.code_blocks) == 2
        assert r.code_blocks[0][0] == "python"
        assert r.code_blocks[1][0] == "bash"

    def test_extract_urls(self) -> None:
        text = "Visit https://example.com and http://test.org/page?q=1"
        r = ArtifactExtractor.extract(text)
        assert len(r.urls) == 2
        assert "https://example.com" in r.urls
        assert "http://test.org/page?q=1" in r.urls

    def test_extract_urls_dedup(self) -> None:
        text = "https://a.com and again https://a.com"
        r = ArtifactExtractor.extract(text)
        assert len(r.urls) == 1

    def test_extract_json_block_valid(self) -> None:
        text = '```json\n{"key": "value"}\n```'
        r = ArtifactExtractor.extract(text)
        assert len(r.json_blocks) == 1
        assert '"key"' in r.json_blocks[0]

    def test_extract_json_block_array(self) -> None:
        text = "```json\n[1, 2, 3]\n```"
        r = ArtifactExtractor.extract(text)
        assert len(r.json_blocks) == 1

    def test_extract_json_block_invalid_ignored(self) -> None:
        text = "```json\nnot valid json\n```"
        r = ArtifactExtractor.extract(text)
        assert r.json_blocks == []

    def test_extract_mixed_content(self) -> None:
        text = (
            "Analysis:\n"
            "https://example.com/report\n\n"
            "```python\nimport os\n```\n\n"
            '```json\n{"status": "ok"}\n```'
        )
        r = ArtifactExtractor.extract(text)
        assert len(r.code_blocks) == 2  # python + json (json is also a code block)
        assert len(r.urls) == 1
        assert len(r.json_blocks) == 1
        assert r.full_text == text

    def test_full_text_preserved(self) -> None:
        text = "Just some plain text with no structure."
        r = ArtifactExtractor.extract(text)
        assert r.full_text == text
        assert r.code_blocks == []
        assert r.urls == []
        assert r.json_blocks == []


# ── MatchToKeys ──


class TestMatchToKeys:
    def test_code_key_matches_code_block(self) -> None:
        extracted = ExtractedContent(
            code_blocks=[("python", "x = 1")],
            full_text="```python\nx = 1\n```",
        )
        result = ArtifactExtractor.match_to_keys(extracted, ["source_code"])
        assert result["source_code"] == "x = 1"

    def test_url_key_matches_urls(self) -> None:
        extracted = ExtractedContent(
            urls=["https://a.com", "https://b.com"],
            full_text="https://a.com https://b.com",
        )
        result = ArtifactExtractor.match_to_keys(extracted, ["reference_urls"])
        assert "https://a.com" in result["reference_urls"]
        assert "https://b.com" in result["reference_urls"]

    def test_data_key_matches_json(self) -> None:
        extracted = ExtractedContent(
            json_blocks=['{"key": "val"}'],
            full_text='```json\n{"key": "val"}\n```',
        )
        result = ArtifactExtractor.match_to_keys(extracted, ["parsed_data"])
        assert result["parsed_data"] == '{"key": "val"}'

    def test_unknown_key_uses_positional_fallback(self) -> None:
        extracted = ExtractedContent(full_text="some text")
        result = ArtifactExtractor.match_to_keys(
            extracted, ["summary"], fallback_values=["The summary"]
        )
        assert result["summary"] == "The summary"

    def test_unknown_key_uses_full_text_when_no_fallback(self) -> None:
        extracted = ExtractedContent(full_text="full output text")
        result = ArtifactExtractor.match_to_keys(extracted, ["summary"])
        assert result["summary"] == "full output text"

    def test_positional_fallback_wraps_around(self) -> None:
        extracted = ExtractedContent(full_text="text")
        result = ArtifactExtractor.match_to_keys(
            extracted, ["a", "b", "c"], fallback_values=["val1"]
        )
        assert result["a"] == "val1"
        assert result["b"] == "val1"  # wraps to first
        assert result["c"] == "val1"

    def test_multiple_code_blocks_assigned_sequentially(self) -> None:
        extracted = ExtractedContent(
            code_blocks=[("py", "block1"), ("js", "block2")],
            full_text="",
        )
        result = ArtifactExtractor.match_to_keys(extracted, ["first_code", "second_code"])
        assert result["first_code"] == "block1"
        assert result["second_code"] == "block2"

    def test_code_keyword_falls_to_positional_when_no_blocks(self) -> None:
        extracted = ExtractedContent(full_text="no code here")
        result = ArtifactExtractor.match_to_keys(
            extracted, ["source_code"], fallback_values=["fallback text"]
        )
        assert result["source_code"] == "fallback text"

    def test_url_keyword_falls_to_positional_when_no_urls(self) -> None:
        extracted = ExtractedContent(full_text="no urls")
        result = ArtifactExtractor.match_to_keys(
            extracted, ["ref_links"], fallback_values=["fallback"]
        )
        assert result["ref_links"] == "fallback"

    def test_data_keyword_falls_to_positional_when_no_json(self) -> None:
        extracted = ExtractedContent(full_text="no json")
        result = ArtifactExtractor.match_to_keys(
            extracted, ["parsed_data"], fallback_values=["raw"]
        )
        assert result["parsed_data"] == "raw"

    def test_empty_keys_returns_empty_dict(self) -> None:
        extracted = ExtractedContent(full_text="text")
        result = ArtifactExtractor.match_to_keys(extracted, [])
        assert result == {}

    def test_hyphenated_key_normalized(self) -> None:
        extracted = ExtractedContent(code_blocks=[("", "x = 1")], full_text="")
        result = ArtifactExtractor.match_to_keys(extracted, ["source-code"])
        assert result["source-code"] == "x = 1"

    def test_mixed_keys_smart_matching(self) -> None:
        """Multiple keys of different types matched correctly."""
        extracted = ExtractedContent(
            code_blocks=[("python", "print(1)")],
            urls=["https://example.com"],
            json_blocks=["[1, 2]"],
            full_text="full",
        )
        result = ArtifactExtractor.match_to_keys(
            extracted,
            ["impl_code", "source_urls", "result_data", "analysis"],
            fallback_values=["text"],
        )
        assert result["impl_code"] == "print(1)"
        assert "https://example.com" in result["source_urls"]
        assert result["result_data"] == "[1, 2]"
        assert result["analysis"] == "text"  # positional fallback


# ── ExtractAndMatch (end-to-end convenience) ──


class TestExtractAndMatch:
    def test_end_to_end_rich_engine_output(self) -> None:
        """Simulates engine output with code, URLs, and plain text."""
        text = (
            "I searched the web and found:\n"
            "https://example.com/result1\n"
            "https://example.com/result2\n\n"
            "Here is the implementation:\n"
            "```python\ndef solve():\n    return 42\n```\n\n"
            "The answer is 42."
        )
        result = ArtifactExtractor.extract_and_match(
            text=text,
            keys=["found_urls", "code_snippet", "summary"],
            fallback_values=[text],
        )
        assert "example.com/result1" in result["found_urls"]
        assert "def solve" in result["code_snippet"]
        assert result["summary"] == text  # no keyword match → fallback

    def test_plain_text_no_structure(self) -> None:
        """No code blocks, URLs, or JSON — all keys get fallback."""
        result = ArtifactExtractor.extract_and_match(
            text="Simple answer: 42",
            keys=["output"],
            fallback_values=["Simple answer: 42"],
        )
        assert result["output"] == "Simple answer: 42"

    def test_no_fallback_uses_full_text(self) -> None:
        result = ArtifactExtractor.extract_and_match(text="The result", keys=["key"])
        assert result["key"] == "The result"

    def test_empty_text_empty_fallback(self) -> None:
        result = ArtifactExtractor.extract_and_match(text="", keys=["key"], fallback_values=[])
        assert result["key"] == ""
