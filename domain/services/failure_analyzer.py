"""FailureAnalyzer — Pure domain service. Extracts tool search queries from errors.

No infrastructure dependencies. Keyword pattern matching only.
LLM-based analysis belongs to Phase 6 (Self-Evolution).
"""

from __future__ import annotations

import re

# Error pattern → search queries mapping
_ERROR_QUERY_MAP: list[tuple[str, list[str]]] = [
    # File system errors
    (r"(?i)file\s*not\s*found|no such file|ENOENT", ["filesystem", "file-manager"]),
    (r"(?i)permission\s*denied|EACCES|EPERM", ["filesystem", "permissions"]),
    (r"(?i)directory\s*not\s*empty|ENOTEMPTY", ["filesystem"]),
    # Database errors
    (
        r"(?i)database|sql|postgres|mysql|sqlite|connection.*refused.*5432",
        ["postgres", "sqlite", "database"],
    ),
    (r"(?i)redis|connection.*refused.*6379", ["redis"]),
    (r"(?i)mongodb|mongo", ["mongodb"]),
    # Web / HTTP errors
    (r"(?i)fetch|http|request|curl|api\s*error|timeout.*http", ["fetch", "http-client"]),
    (r"(?i)CORS|cross-origin", ["cors", "proxy"]),
    (r"(?i)webhook|callback.*url", ["webhook"]),
    # Git / Version control
    (r"(?i)git\s*clone|git\s*pull|git\s*push|repository", ["git", "github"]),
    # Docker / Container
    (r"(?i)docker|container|image.*not.*found", ["docker"]),
    # Package / Dependency
    (r"(?i)module.*not.*found|import\s*error|no\s*module|ModuleNotFoundError", ["package-manager"]),
    (r"(?i)npm\s*ERR|yarn\s*error|pip.*install.*failed", ["package-manager"]),
    # Authentication
    (r"(?i)auth|token|credential|unauthorized|403|401", ["auth", "secrets"]),
    (r"(?i)oauth|jwt|api.key", ["auth", "oauth"]),
    # Search / Scraping
    (r"(?i)search|scrape|crawl|extract.*web|parse.*html", ["web-search", "scraper"]),
    (r"(?i)browser|playwright|selenium|puppeteer", ["browser", "playwright"]),
    # Email / Messaging
    (r"(?i)email|smtp|mail|sendgrid", ["email", "smtp"]),
    (r"(?i)slack|discord|telegram", ["slack", "discord"]),
    # Cloud / Storage
    (r"(?i)s3|aws|bucket|storage|blob", ["aws", "s3", "storage"]),
    (r"(?i)gcs|google.*cloud|firebase", ["google-cloud", "firebase"]),
]


class FailureAnalyzer:
    """Extract MCP search queries from error messages.

    Pure domain logic — no I/O, no external dependencies.
    """

    def extract_queries(self, error_message: str) -> list[str]:
        """Extract relevant tool search queries from an error message.

        Returns deduplicated list of search queries, most relevant first.
        """
        queries: list[str] = []
        seen: set[str] = set()

        for pattern, query_list in _ERROR_QUERY_MAP:
            if re.search(pattern, error_message):
                for q in query_list:
                    if q not in seen:
                        queries.append(q)
                        seen.add(q)

        return queries

    def extract_queries_with_context(
        self,
        error_message: str,
        task_description: str = "",
    ) -> list[str]:
        """Extract queries using both error and task context.

        Combines error pattern matching with task keyword extraction.
        """
        queries = self.extract_queries(error_message)

        # Also extract keywords from task description
        if task_description:
            task_queries = self._extract_task_keywords(task_description)
            seen = set(queries)
            for q in task_queries:
                if q not in seen:
                    queries.append(q)
                    seen.add(q)

        return queries

    def _extract_task_keywords(self, task_description: str) -> list[str]:
        """Extract search keywords from a task description."""
        keywords: list[str] = []
        text = task_description.lower()

        keyword_map: dict[str, str] = {
            "file": "filesystem",
            "database": "database",
            "api": "http-client",
            "web": "web-search",
            "git": "git",
            "docker": "docker",
            "email": "email",
            "slack": "slack",
            "browser": "browser",
            "search": "web-search",
            "auth": "auth",
            "storage": "storage",
        }

        for word, query in keyword_map.items():
            if word in text and query not in keywords:
                keywords.append(query)

        return keywords
