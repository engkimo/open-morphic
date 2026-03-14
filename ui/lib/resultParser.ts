/** Result parser — detect content type from subtask result. */

export type ResultType = "code" | "json" | "text";

export interface ParsedResult {
  type: ResultType;
  content: string;
  language?: string;
}

/**
 * Parse a subtask result string and detect its type.
 * Priority: JSON > code block > plain text.
 */
export function parseResult(result: string | null): ParsedResult {
  if (!result) {
    return { type: "text", content: "" };
  }

  const trimmed = result.trim();

  // Detect JSON
  if (
    (trimmed.startsWith("{") && trimmed.endsWith("}")) ||
    (trimmed.startsWith("[") && trimmed.endsWith("]"))
  ) {
    try {
      const parsed = JSON.parse(trimmed);
      return {
        type: "json",
        content: JSON.stringify(parsed, null, 2),
        language: "json",
      };
    } catch {
      // Not valid JSON, fall through
    }
  }

  // Detect fenced code blocks in the result
  const codeMatch = trimmed.match(/```(\w+)?\s*\n([\s\S]*?)```/);
  if (codeMatch) {
    return {
      type: "code",
      content: codeMatch[2].trim(),
      language: codeMatch[1] || "text",
    };
  }

  return { type: "text", content: trimmed };
}
