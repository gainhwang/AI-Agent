"""MCP tool for retrieving clause candidates from parsed policy PDFs.

The API validates and extracts each PDF once. This server receives that parsed
document, then runs the same topic-specific retrieval used by the CLI.
"""

from fastmcp import FastMCP

from .generic_evidence import TOPICS, find_candidates


mcp = FastMCP(name="insurance-policy-evidence")


@mcp.tool()
def search_policy_evidence(document: dict, topics: list[str]) -> dict:
    """Return ranked, page-numbered clause excerpts for the requested topics."""
    if not topics or any(topic not in TOPICS for topic in topics):
        raise ValueError("지원하지 않는 비교 항목입니다.")
    if not isinstance(document.get("pages"), list) or len(document["pages"]) > 500:
        raise ValueError("PDF 페이지 정보가 올바르지 않습니다.")
    return {topic: find_candidates(document, topic) for topic in topics}


if __name__ == "__main__":
    try:
        mcp.run(show_banner=False)
    except TypeError:
        mcp.run()
