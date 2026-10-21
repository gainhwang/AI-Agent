"""LangGraph workflow: MCP retrieval, four specialist comparisons, validation."""

import asyncio
import operator
from dataclasses import dataclass
from functools import partial
from typing import Annotated, TypedDict

from langgraph.graph import END, StateGraph
from langsmith import traceable

from .generic_compare import build_output, compare_documents
from .generic_evidence import TOPICS
from .scoped_rules import unclear


class PolicyState(TypedDict, total=False):
    documents: dict
    topics: list[str]
    candidates: dict
    results: Annotated[list[dict], operator.add]
    output: dict


@dataclass(frozen=True)
class PolicyDeps:
    evidence_client: object
    comparer: object = compare_documents
    formatter: object = build_output


@traceable(name="policy_retrieve_node")
async def retrieve_node(state: PolicyState, deps: PolicyDeps) -> dict:
    """The MCP tool supplies page-numbered excerpts for each PDF."""
    candidates = {}
    for side in ("left", "right"):
        candidates[side] = await deps.evidence_client.retrieve(
            state["documents"][side], state["topics"]
        )
    return {"candidates": candidates}


@traceable(name="policy_compare_node")
async def compare_node(state: PolicyState, topic: str, deps: PolicyDeps) -> dict:
    """A topic specialist compares only its own clause type."""
    if topic not in state["topics"]:
        return {"results": []}
    candidates = {
        side: state["candidates"][side][topic]
        for side in ("left", "right")
    }
    try:
        checked, notes = await asyncio.to_thread(
            deps.comparer, topic, state["documents"], candidates
        )
    except Exception:
        checked, notes = unclear(
            "이 항목의 AI 비교를 완료하지 못했습니다. 원문을 확인하세요."
        )
    item = deps.formatter(topic, state["documents"], checked, notes)
    return {"results": [{"key": topic, **item}]}


@traceable(name="policy_validate_node")
async def validate_node(state: PolicyState) -> dict:
    """Keep output order stable and never publish an unsupported conclusion."""
    indexed = {item["key"]: item for item in state["results"]}
    results = []
    for topic in state["topics"]:
        item = indexed[topic]
        if item["comparison_status"] != "unclear" and any(
            not item[side]["evidence"] for side in ("left", "right")
        ):
            item = dict(item)
            item["comparison_status"] = "unclear"
            item["comparison"] = "근거가 부족하여 두 약관의 차이는 확인 필요합니다."
            item["validation_notes"] = [
                *item["validation_notes"], "근거가 없는 비교 결론을 보류했습니다."
            ]
        results.append(item)
    return {"output": {
        "first_file": state["documents"]["left"]["file"],
        "second_file": state["documents"]["right"]["file"],
        "results": results,
        "workflow": {"graph": "policy_comparison", "retrieval": "mcp_tool"},
    }}


def build_graph(deps: PolicyDeps):
    graph = StateGraph(PolicyState)
    graph.add_node("retrieve", partial(retrieve_node, deps=deps))
    workers = []
    for topic in TOPICS:
        name = f"compare_{topic}"
        graph.add_node(name, partial(compare_node, topic=topic, deps=deps))
        graph.add_edge("retrieve", name)
        workers.append(name)
    graph.add_node("validate", validate_node)
    graph.add_edge(workers, "validate")
    graph.add_edge("validate", END)
    graph.set_entry_point("retrieve")
    return graph.compile()
