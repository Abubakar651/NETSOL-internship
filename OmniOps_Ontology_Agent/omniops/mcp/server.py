"""Standards-compliant MCP Server supporting in-process Python, JSON-RPC 2.0 HTTP, and Stdio."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, TextIO

from omniops.graph import (
    CedarPolicyEvaluator,
    KineticActionExecutor,
    OmnigraphBranchManager,
    SemanticGraphEngine,
)
from omniops.ontology import (
    AnswerabilityChecker,
    AutoOntologyScanner,
    OntologyRegistry,
    create_seeded_database,
)

from .prompts import MCPPromptProvider, UnknownPromptError
from .resources import MCPResourceProvider, ResourceNotFoundError
from .tools import MCPToolRegistry, ToolCallTrace, ToolInputError, UnknownToolError

_PROTOCOL_VERSION = "2024-11-05"


class OmniOpsMCPServer:
    """Unified Model Context Protocol Server backed by OmniOps Ontology & Omnigraph."""

    def __init__(
        self,
        registry: OntologyRegistry,
        answerability: AnswerabilityChecker,
        branch_manager: OmnigraphBranchManager,
        action_executor: KineticActionExecutor,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        self.registry = registry
        self.answerability = answerability
        self.branch_manager = branch_manager
        self.action_executor = action_executor
        self._conn = conn

        self.resources = MCPResourceProvider(registry, branch_manager)
        self.tools = MCPToolRegistry(registry, answerability, branch_manager, action_executor)
        self.prompts = MCPPromptProvider()

    @classmethod
    def from_seeded_database(cls, db_path: str | Path = ":memory:") -> OmniOpsMCPServer:
        """Bootstrap a complete seeded Ontology -> Omnigraph -> MCP Server stack."""
        conn = create_seeded_database(db_path)
        catalog = AutoOntologyScanner(conn).discover()
        registry = OntologyRegistry(catalog, conn)
        answerability = AnswerabilityChecker(registry)
        graph_engine = SemanticGraphEngine.from_registry(registry)
        branch_manager = OmnigraphBranchManager(graph_engine.snapshot, author="system")
        action_executor = KineticActionExecutor(branch_manager, CedarPolicyEvaluator())
        return cls(
            registry=registry,
            answerability=answerability,
            branch_manager=branch_manager,
            action_executor=action_executor,
            conn=conn,
        )

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # --- In-process Python convenience methods ---

    def list_resources(self) -> list[dict[str, str]]:
        return self.resources.list_resources()

    def list_resource_templates(self) -> list[dict[str, str]]:
        return self.resources.list_resource_templates()

    def read_resource(self, uri: str) -> dict[str, Any]:
        return self.resources.read_resource(uri)

    def list_tools(self) -> list[dict[str, Any]]:
        return self.tools.list_tools()

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.tools.call_tool(name, arguments)

    def list_prompts(self) -> list[dict[str, Any]]:
        return self.prompts.list_prompts()

    def get_prompt(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.prompts.get_prompt(name, arguments)

    def get_trace_log(self) -> list[ToolCallTrace]:
        return self.tools.get_trace_log()

    def clear_trace_log(self) -> None:
        self.tools.clear_trace_log()

    # --- JSON-RPC 2.0 Protocol Dispatcher ---

    @staticmethod
    def _ok(req_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    @staticmethod
    def _error(req_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}

    def handle_jsonrpc(self, request: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
            return self._error(
                request.get("id") if isinstance(request, dict) else None,
                -32600,
                "Invalid JSON-RPC 2.0 Request.",
            )

        method = request.get("method")
        if not isinstance(method, str) or not method:
            return self._error(request.get("id"), -32600, "Missing JSON-RPC 'method'.")

        req_id = request.get("id")
        if method.startswith("notifications/") or req_id is None and method == "notifications/initialized":
            return None

        params = request.get("params")
        if params is None:
            params = {}
        elif not isinstance(params, dict):
            return self._error(req_id, -32602, "JSON-RPC 'params' must be an object.")

        try:
            if method == "initialize":
                return self._ok(
                    req_id,
                    {
                        "protocolVersion": _PROTOCOL_VERSION,
                        "capabilities": {
                            "resources": {"subscribe": False, "listChanged": False},
                            "tools": {"listChanged": False},
                            "prompts": {"listChanged": False},
                        },
                        "serverInfo": {"name": "omniops-ontology-mcp", "version": "1.0.0"},
                    },
                )

            if method == "ping":
                return self._ok(req_id, {})

            if method == "resources/list":
                return self._ok(req_id, {"resources": self.list_resources()})

            if method == "resources/templates/list":
                return self._ok(req_id, {"resourceTemplates": self.list_resource_templates()})

            if method == "resources/read":
                uri = params.get("uri")
                if not isinstance(uri, str) or not uri.strip():
                    raise ValueError("Method 'resources/read' requires string parameter 'uri'.")
                res = self.read_resource(uri)
                return self._ok(req_id, {"contents": res["contents"]})

            if method == "tools/list":
                return self._ok(req_id, {"tools": self.list_tools()})

            if method == "tools/call":
                tool_name = params.get("name")
                if not isinstance(tool_name, str) or not tool_name.strip():
                    raise ToolInputError("Method 'tools/call' requires string parameter 'name'.")
                arguments = params.get("arguments")
                if arguments is not None and not isinstance(arguments, dict):
                    raise ToolInputError("Parameter 'arguments' must be an object.")
                res = self.call_tool(tool_name, arguments)
                return self._ok(req_id, {"content": res["content"], "isError": res["isError"]})

            if method == "prompts/list":
                return self._ok(req_id, {"prompts": self.list_prompts()})

            if method == "prompts/get":
                prompt_name = params.get("name")
                if not isinstance(prompt_name, str) or not prompt_name.strip():
                    raise ValueError("Method 'prompts/get' requires string parameter 'name'.")
                prompt_args = params.get("arguments")
                if prompt_args is not None and not isinstance(prompt_args, dict):
                    raise ValueError("Parameter 'arguments' must be an object.")
                res = self.get_prompt(prompt_name, prompt_args)
                return self._ok(req_id, res)

            return self._error(req_id, -32601, f"Method '{method}' not found.")

        except (
            ResourceNotFoundError,
            UnknownToolError,
            ToolInputError,
            UnknownPromptError,
            ValueError,
        ) as exc:
            return self._error(req_id, -32602, str(exc))
        except Exception as exc:  # pragma: no cover - defensive fallback
            return self._error(req_id, -32603, f"Internal error: {exc}")

    def serve_stdio(self, stdin: TextIO | None = None, stdout: TextIO | None = None) -> None:
        """Run a line-delimited JSON-RPC 2.0 MCP loop over stdio streams."""
        in_stream = stdin or sys.stdin
        out_stream = stdout or sys.stdout
        for raw_line in in_stream:
            line = raw_line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
            except json.JSONDecodeError as exc:
                resp = self._error(None, -32700, f"Parse error: {exc}")
            else:
                resp = self.handle_jsonrpc(request)
            if resp is not None:
                out_stream.write(json.dumps(resp) + "\n")
                out_stream.flush()


if __name__ == "__main__":  # pragma: no cover
    server = OmniOpsMCPServer.from_seeded_database()
    try:
        server.serve_stdio()
    finally:
        server.close()
