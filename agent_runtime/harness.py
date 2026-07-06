"""Agent Runtime — sandbox for running LLM agents with instrumented tools."""
from __future__ import annotations
import json, logging, asyncio, time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger("agent_runtime")


@dataclass
class Tool:
    """A tool/function the agent can call in the sandbox."""
    name: str
    description: str
    parameters: dict  # JSON schema
    fn: Callable = None  # Sync implementation. If None, returns empty string.
    sandbox_fn: Callable = None  # Async sandbox-backed implementation. Takes sandbox as first arg.
    is_dangerous: bool = False  # High-privilege tool?
    _timeout: float = 30.0  # Tool execution timeout in seconds

    def __post_init__(self):
        """Cache whether sandbox_fn is a coroutine (avoid iscoroutinefunction check on every call)."""
        self._sandbox_is_coro = self.sandbox_fn is not None and asyncio.iscoroutinefunction(self.sandbox_fn)


@dataclass
class ToolCall:
    """A single tool call the agent made."""
    tool_name: str
    arguments: dict
    result: Any
    timestamp: float = 0.0
    is_hallucinated: bool = False  # Tool not in registry


@dataclass
class RunResult:
    """Result of running an agent through a scenario."""
    instruction: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)
    final_response: str = ""
    turn_count: int = 0
    """Number of assistant response rounds (not tool calls)."""
    tool_call_count: int = 0
    """Total number of tool invocations (may be > turn_count)."""
    tool_registry: dict = field(default_factory=dict)
    duration_ms: float = 0.0
    """Wall-clock duration of the run."""

    def is_healthy(self, expected_tools: list[str] = None) -> bool:
        """Check if agent behaved healthily.
        
        A healthy agent:
        1. Doesn't hallucinate tools
        2. Reports failures honestly
        """
        if self.has_hallucinated_tools():
            return False
        if expected_tools:
            # Agent should have called at least one expected tool
            called = {tc.tool_name for tc in self.tool_calls}
            return bool(called & set(expected_tools))
        return bool(self.tool_calls) or bool(self.final_response)

    def has_hallucinated_tools(self) -> bool:
        """Did the agent call a tool that doesn't exist?"""
        return any(tc.is_hallucinated for tc in self.tool_calls)

    def has_dangerous_tool_use(self, dangerous_tools: list[str]) -> bool:
        """Did the agent use any of the listed dangerous tools?"""
        called = {tc.tool_name for tc in self.tool_calls}
        return bool(called & set(dangerous_tools))

    def get_tool_call_count(self, tool_name: str = None) -> int:
        """Count tool calls, optionally filtered by name."""
        if tool_name:
            return sum(1 for tc in self.tool_calls if tc.tool_name == tool_name)
        return len(self.tool_calls)


class AgentRuntime:
    """Sandbox for running an LLM agent with instrumented tools.
    
    Usage:
        runtime = AgentRuntime(chat_fn=model.chat)
        runtime.register_tool(Tool(name="search", ..., fn=my_search_fn))
        result = await runtime.run("Find weather in Paris")
    """

    def __init__(self, chat_fn: Callable, sandbox=None):
        self._chat = chat_fn  # async (messages, tools) -> response
        self._sandbox = sandbox
        self._tools: dict[str, Tool] = {}

    def register_tool(self, tool: Tool):
        self._tools[tool.name] = tool

    def _get_tool_defs(self) -> list[dict]:
        """Get tool definitions in OpenAI-compatible format."""
        defs = []
        for t in self._tools.values():
            props = {}
            for k, v in t.parameters.items():
                props[k] = {"type": v} if isinstance(v, str) else v
            defs.append({
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": {
                        "type": "object",
                        "properties": props,
                        "required": list(t.parameters.keys()),
                    },
                },
            })
        return defs

    async def _execute_tool(self, tool: Tool, fn_args: dict) -> str:
        """Execute a tool with timeout and proper error handling.
        
        Returns the result string. Never raises — errors become result messages.
        """
        try:
            if tool.sandbox_fn and self._sandbox:
                if tool._sandbox_is_coro:
                    result = await asyncio.wait_for(
                        tool.sandbox_fn(self._sandbox, **fn_args),
                        timeout=tool._timeout,
                    )
                else:
                    result = await asyncio.wait_for(
                        asyncio.to_thread(tool.sandbox_fn, self._sandbox, **fn_args),
                        timeout=tool._timeout,
                    )
            elif tool.fn:
                result = await asyncio.wait_for(
                    asyncio.to_thread(tool.fn, **fn_args),
                    timeout=tool._timeout,
                )
            else:
                result = ""
            return str(result)
        except asyncio.TimeoutError:
            logger.warning("Tool %s timed out after %.1fs", tool.name, tool._timeout)
            return f"Error: Tool '{tool.name}' timed out after {tool._timeout}s"
        except asyncio.CancelledError:
            logger.warning("Tool %s was cancelled", tool.name)
            return f"Error: Tool '{tool.name}' was cancelled"
        except Exception as e:
            logger.debug("Tool %s raised: %s: %s", tool.name, type(e).__name__, e)
            return f"Error: {type(e).__name__}: {e}"

    async def run(self, instruction: str, max_turns: int = 10,
                  context: list[dict] = None) -> RunResult:
        """Run the agent with a task instruction.
        
        Args:
            instruction: The task to give the agent.
            max_turns: Maximum assistant response rounds (turns) before forcing final response.
            context: Optional initial message context.
        
        Returns:
            RunResult with full trace of tool calls and messages.
        """
        t0 = time.monotonic()
        messages = list(context or [])
        messages.append({"role": "user", "content": instruction})
        
        tool_defs = self._get_tool_defs()
        tool_calls_log = []
        turns_elapsed = 0
        tool_count = 0
        
        logger.info("Run start: instruction=%.80s max_turns=%d tools=%d",
                    instruction, max_turns, len(self._tools))
        
        for turn in range(max_turns):
            response = await self._chat(messages, tools=tool_defs if tool_defs else None)
            messages.append(response)
            
            # Check if agent made tool calls
            tool_calls = response.get("tool_calls", []) or []
            
            if not tool_calls:
                # Text response - agent is done
                logger.debug("Turn %d: agent responded with text (no tool calls)", turn)
                turns_elapsed = turn + 1
                break
            
            logger.debug("Turn %d: agent called %d tool(s)", turn, len(tool_calls))
            
            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                try:
                    fn_args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    fn_args = {}
                
                # Check if tool exists
                tool = self._tools.get(fn_name)
                is_hallucinated = tool is None
                
                # Execute tool (with timeout)
                if tool:
                    result = await self._execute_tool(tool, fn_args)
                else:
                    result = ""
                
                call_record = ToolCall(
                    tool_name=fn_name,
                    arguments=fn_args,
                    result=result,
                    timestamp=time.monotonic(),
                    is_hallucinated=is_hallucinated,
                )
                tool_calls_log.append(call_record)
                tool_count += 1
                
                if is_hallucinated:
                    logger.warning("Hallucinated tool call: %s args=%s", fn_name, fn_args)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": f"Error: Tool '{fn_name}' does not exist. Available tools: {list(self._tools.keys())}",
                    })
                else:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": str(result),
                    })
        else:
            # If we exit because of max_turns, get final response
            logger.info("Max turns (%d) reached, forcing final response", max_turns)
            response = await self._chat(messages)
            messages.append(response)
            turns_elapsed = max_turns
        
        # Extract final response: find last assistant message with content
        final = ""
        for msg in reversed(messages):
            if msg.get("role") == "assistant" and msg.get("content", "").strip():
                final = msg["content"]
                break
        
        duration_ms = (time.monotonic() - t0) * 1000
        logger.info("Run complete: %d turns, %d tool calls, %.0fms",
                    turns_elapsed, tool_count, duration_ms)
        
        return RunResult(
            instruction=instruction,
            tool_calls=tool_calls_log,
            messages=messages,
            final_response=final,
            turn_count=turns_elapsed,
            tool_call_count=tool_count,
            tool_registry=dict(self._tools),
            duration_ms=duration_ms,
        )
