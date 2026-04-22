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

/** Complexity-aware parsed result with answer/reasoning separation. */
export interface ComplexityParsedResult {
  answer: string;
  reasoning: string | null;
  parsed: ParsedResult;
}

const THINK_TAG_RE = /<think>([\s\S]*?)<\/think>/g;

/**
 * Parse result with complexity awareness.
 * For SIMPLE tasks: extract just the core answer.
 * For MEDIUM/COMPLEX: separate answer from reasoning (<think> tags).
 */
export function parseResultWithComplexity(
  result: string | null,
  complexity: string | null,
): ComplexityParsedResult {
  if (!result) {
    return { answer: "", reasoning: null, parsed: { type: "text", content: "" } };
  }

  // Extract reasoning from <think> tags
  let reasoning: string | null = null;
  const thinkMatches = [...result.matchAll(THINK_TAG_RE)];
  if (thinkMatches.length > 0) {
    reasoning = thinkMatches.map((m) => m[1].trim()).join("\n\n");
  }

  // Strip <think> tags from the answer
  const cleanedResult = result.replace(THINK_TAG_RE, "").trim();
  const parsed = parseResult(cleanedResult);

  // For simple tasks, the parsed content IS the answer
  const answer = parsed.type === "text" ? parsed.content : cleanedResult;

  // For simple tasks, suppress reasoning
  if (complexity === "simple") {
    return { answer, reasoning: null, parsed };
  }

  return { answer, reasoning, parsed };
}
