"""A reusable stdio MCP client for the policy evidence server."""

import json
import os
import sys
from contextlib import AsyncExitStack

from langsmith import traceable
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class PolicyEvidenceClient:
    def __init__(self):
        self._stack = None
        self._session = None

    async def __aenter__(self):
        self._stack = AsyncExitStack()
        try:
            params = StdioServerParameters(
                command=sys.executable,
                args=["-m", "insurance_compare.policy_mcp_server"],
                env={**os.environ, "FASTMCP_LOG_LEVEL": "ERROR"},
            )
            read, write = await self._stack.enter_async_context(stdio_client(params))
            self._session = await self._stack.enter_async_context(ClientSession(read, write))
            await self._session.initialize()
            return self
        except Exception:
            await self._stack.aclose()
            raise

    async def __aexit__(self, exc_type, exc, tb):
        await self._stack.aclose()
        self._session = None

    @traceable(run_type="tool", name="mcp.search_policy_evidence")
    async def retrieve(self, document, topics):
        response = await self._session.call_tool(
            "search_policy_evidence", {"document": document, "topics": topics}
        )
        if getattr(response, "is_error", getattr(response, "isError", False)) or not response.content:
            raise RuntimeError("MCP 근거 검색에 실패했습니다.")
        return json.loads(response.content[0].text)
