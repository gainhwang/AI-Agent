"""Compare policy topics through the LangGraph and MCP evidence workflow."""
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# The base project may enable LangSmith in .env. Policy documents can include
# sensitive health data, so turn tracing off before importing graph/trace code
# unless this workflow was explicitly opted in for public demo PDFs.
load_dotenv()
POLICY_TRACING_ENABLED = os.getenv("POLICY_LANGSMITH_TRACING") == "1"
if not POLICY_TRACING_ENABLED:
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"

from langsmith import tracing_context

from .generic_evidence import TOPICS
from .pdf_input import load_pdf
from .policy_graph import PolicyDeps, build_graph
from .policy_mcp_client import PolicyEvidenceClient


async def compare_async(documents, topics):
    async with PolicyEvidenceClient() as evidence_client:
        graph = build_graph(PolicyDeps(evidence_client=evidence_client))
        # PDF text contains potentially sensitive health information. Tracing
        # stays off unless the presenter explicitly opts in with demo PDFs.
        with tracing_context(enabled=POLICY_TRACING_ENABLED):
            state = await graph.ainvoke({
                "documents": documents,
                "topics": topics,
                "results": [],
            })
        return state["output"]


def compare_all(documents, topics=None):
    chosen = list(TOPICS) if topics is None else list(topics)
    if not chosen or any(topic not in TOPICS for topic in chosen):
        raise ValueError("지원하지 않는 비교 항목입니다.")
    return asyncio.run(compare_async(documents, chosen))


def main():
    args = sys.argv[1:]
    if len(args) == 4 and args[0] == "--topic" and args[1] in TOPICS:
        topics = [args[1]]
        filenames = args[2:]
    elif len(args) == 2:
        topics = list(TOPICS)
        filenames = args
    else:
        raise SystemExit(
            "사용법: python -m insurance_compare.compare_all "
            "[--topic therapy|deductible|limit|exclusion] 첫번째.pdf 두번째.pdf"
        )
    documents = {
        side: load_pdf(Path(filename).name, Path(filename).read_bytes())
        for side, filename in zip(("left", "right"), filenames)
    }
    output = compare_all(documents, topics)
    if len(topics) == 1:
        output = output["results"][0]
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
