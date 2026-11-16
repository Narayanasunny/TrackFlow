"""Session-aware LangGraph tool-calling workflow for TrackFlow.

Groq interprets requests and chooses tools. Existing Python simulation,
OR-Tools optimization, and schedule validation remain authoritative.

Conversation context is bounded: older turns are compacted into a rolling
extractive summary, recent turns are retained, and large tool payloads are
kept in graph state but represented compactly in messages sent to Groq.
"""
from __future__ import annotations

import json
import logging
from typing import Annotated, Any
from typing_extensions import TypedDict

from langchain_core.messages import (
    AIMessage, BaseMessage, HumanMessage, RemoveMessage,
    SystemMessage, ToolMessage,
)
from langchain_core.tools import InjectedToolCallId, tool
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import InjectedState, ToolNode
from langgraph.types import Command

from backend.app.agents.traffic_analysis_agent import analyze_traffic
from backend.app.agents.dynamic_rescheduling_agent import run_dynamic_rescheduling
from backend.app.agents.explainability_agent import explain_optimization
from backend.app.schedule_validator import validate_optimized_schedule

logger = logging.getLogger("trackflow.agent")

# Keep the model's input substantially below the configured 8k TPM ceiling.
MODEL_NAME = "openai/gpt-oss-20b"
MAX_RECENT_MESSAGES = 8
MAX_MESSAGE_CHARS = 1800
MAX_MEMORY_CHARS = 4200
MAX_TOOL_MESSAGE_CHARS = 2200


def get_groq_llm() -> ChatGroq:
    return ChatGroq(
        model=MODEL_NAME,
        temperature=0,
        max_retries=0,  # Avoid long automatic retries after 413/429 responses.
    )


class TrackFlowState(TypedDict, total=False):
    user_request: str
    messages: Annotated[list[BaseMessage], add_messages]
    baseline_trains: list[dict[str, Any]]
    track_sections: list[dict[str, Any]]
    disruptions: list[dict[str, Any]]
    traffic_analysis: dict[str, Any]
    rescheduling_result: dict[str, Any]
    explanation: dict[str, Any]
    tools_used: list[str]
    last_traffic_analysis: dict[str, Any]
    last_rescheduling_result: dict[str, Any]
    last_explanation: dict[str, Any]
    last_disruptions: list[dict[str, Any]]
    conversation_summary: str
    final_response: str
    error: str


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _message_text(message: BaseMessage | None) -> str:
    if message is None:
        return ""
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                value = item.get("text")
                if isinstance(value, str) and value.strip():
                    parts.append(value.strip())
        return "\n".join(parts)
    return ""


def _clip(value: Any, limit: int = MAX_MESSAGE_CHARS) -> str:
    text = value if isinstance(value, str) else _json_text(value)
    if len(text) <= limit:
        return text
    return text[:limit] + "\n[content shortened to control model token usage]"


def _compact_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    """Keep decision-relevant network metrics, not verbose raw records."""
    if not isinstance(analysis, dict):
        return {"result": _clip(analysis, 500)}
    keys = (
        "network_summary", "conflict_types", "most_affected_trains",
        "most_affected_sections", "recommendations", "summary",
    )
    compact = {key: analysis[key] for key in keys if key in analysis}
    if not compact:
        compact = {key: value for key, value in list(analysis.items())[:12]}
    return compact


def _compact_optimization(result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {"result": _clip(result, 500)}
    validation = result.get("validation") or {}
    return {
        "status": result.get("status"),
        "total_added_departure_delay_minutes": result.get("total_added_departure_delay_minutes"),
        "optimized_train_count": len(result.get("optimized_trains") or []),
        "remaining_conflict_count": len(result.get("remaining_conflicts") or []),
        "remaining_conflicts_sample": (result.get("remaining_conflicts") or [])[:5],
        "validation": {
            "passed": validation.get("passed", validation.get("is_valid")),
            "conflict_count": validation.get("conflict_count"),
            "integrity_errors": (validation.get("integrity_errors") or [])[:5],
        },
        "recommendations": (result.get("recommendations") or [])[:5],
        "message": result.get("message"),
    }


def _tool_command(*, update: dict[str, Any], tool_call_id: str, content: str) -> Command:
    return Command(update={**update, "messages": [ToolMessage(
        content=_clip(content, MAX_TOOL_MESSAGE_CHARS), tool_call_id=tool_call_id
    )]})


def _record_tool(state: TrackFlowState, name: str) -> list[str]:
    used = list(state.get("tools_used") or [])
    if name not in used:
        used.append(name)
    return used


def _analysis_fallback(analysis: dict[str, Any]) -> str:
    network = analysis.get("network_summary") or {}
    lines = ["## Current railway traffic analysis", ""]
    if isinstance(network, dict):
        labels = (
            ("train_count", "Trains"), ("station_count", "Stations"),
            ("track_section_count", "Track sections"),
            ("baseline_conflict_count", "Detected conflicts"),
            ("total_delay_minutes", "Baseline delay minutes"),
        )
        facts = [f"{label}: {network[key]}" for key, label in labels if network.get(key) is not None]
        if facts:
            lines.append("; ".join(facts) + ".")
    conflict_types = analysis.get("conflict_types") or []
    if conflict_types:
        lines.extend(["", "**Conflict breakdown:**"])
        for item in conflict_types[:8]:
            if isinstance(item, dict):
                lines.append(f"- {str(item.get('type', 'unknown')).replace('_', ' ').title()}: {item.get('count', 'not reported')}")
    for key, heading in (("most_affected_trains", "Most affected trains"), ("most_affected_sections", "Most affected track sections")):
        values = analysis.get(key) or []
        if values:
            lines.extend(["", f"**{heading}:**"])
            for item in values[:5]:
                lines.append(f"- {_clip(item, 250)}")
    lines.extend(["", "These are recommendations only; no new schedule was optimized.",
                  "TrackFlow uses a synthetic model and is not authorization for real railway operation."])
    return "\n".join(lines)


def _optimization_fallback(state: TrackFlowState) -> str:
    result = state.get("rescheduling_result") or state.get("last_rescheduling_result") or {}
    validation = result.get("validation") or {}
    disruptions = state.get("disruptions") or state.get("last_disruptions") or []
    if not result:
        return state.get("error") or "No optimization result is available in this conversation."
    lines = ["## Optimization result", ""]
    for item in disruptions:
        lines.append(f"- Track closure: {item.get('section_id')} from minute {item.get('start_minute')} to {item.get('end_minute')}")
    lines.extend([
        f"- Solver status: {result.get('status', 'Not reported')}",
        f"- Total additional departure delay: {result.get('total_added_departure_delay_minutes', 'Not reported')} minutes",
        f"- Remaining conflicts: {len(result.get('remaining_conflicts') or [])}",
        f"- Configured validation: {'passed' if validation.get('passed', validation.get('is_valid', False)) else 'not passed / not reported'}",
    ])
    explanation = state.get("explanation") or state.get("last_explanation") or {}
    if explanation.get("summary"):
        lines.extend(["", str(explanation["summary"])])
    if state.get("error"):
        lines.extend(["", f"Tool error: {state['error']}"])
    lines.extend(["", "This is a synthetic decision-support result, not authorization for real-world railway operation."])
    return "\n".join(lines)


# ----------------------------- Tools ---------------------------------------

@tool("analyze_rail_traffic")
def analyze_rail_traffic_tool(
    state: Annotated[TrackFlowState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Analyze the current synthetic railway network and return conflict hotspots."""
    try:
        analysis = analyze_traffic()
        return _tool_command(
            update={"traffic_analysis": analysis, "tools_used": _record_tool(state, "analyze_rail_traffic"), "error": ""},
            tool_call_id=tool_call_id,
            content=_json_text(_compact_analysis(analysis)),
        )
    except Exception as exc:
        logger.exception("Traffic analysis tool failed")
        message = f"Traffic analysis tool failed: {exc}"
        return _tool_command(update={"error": message, "tools_used": _record_tool(state, "analyze_rail_traffic")}, tool_call_id=tool_call_id, content=message)


@tool("reschedule_after_track_closure")
def reschedule_after_track_closure_tool(
    section_id: str,
    start_minute: int,
    end_minute: int,
    state: Annotated[TrackFlowState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Apply a specified temporary track closure, optimize with OR-Tools, and validate."""
    used = _record_tool(state, "reschedule_after_track_closure")
    sections = state.get("track_sections") or []
    trains = state.get("baseline_trains") or []
    if not section_id.strip() or start_minute < 0 or end_minute <= start_minute:
        message = "Invalid closure. Supply a valid section ID, non-negative start, and end greater than start."
        return _tool_command(update={"error": message, "tools_used": used}, tool_call_id=tool_call_id, content=message)
    if not trains or not sections:
        message = "The API did not provide baseline trains and track sections. No optimization was run."
        return _tool_command(update={"error": message, "tools_used": used}, tool_call_id=tool_call_id, content=message)
    if not any(item.get("section_id") == section_id for item in sections):
        message = f"Track section {section_id} was not found. No optimization was run."
        return _tool_command(update={"error": message, "tools_used": used}, tool_call_id=tool_call_id, content=message)
    disruption = {"section_id": section_id, "start_minute": start_minute, "end_minute": end_minute}
    disruptions = list(state.get("disruptions") or []) + [disruption]
    try:
        result = run_dynamic_rescheduling(
            baseline_trains=trains,
            track_sections=sections,
            validate_schedule=validate_optimized_schedule,
            disruptions=disruptions,
        )
        return _tool_command(
            update={"disruptions": disruptions, "rescheduling_result": result, "tools_used": used, "error": ""},
            tool_call_id=tool_call_id,
            content=_json_text(_compact_optimization(result)),
        )
    except Exception as exc:
        logger.exception("Track-closure rescheduling tool failed")
        message = f"Track-closure rescheduling failed: {exc}"
        return _tool_command(update={"disruptions": disruptions, "error": message, "tools_used": used}, tool_call_id=tool_call_id, content=message)


@tool("explain_schedule_changes")
def explain_schedule_changes_tool(
    state: Annotated[TrackFlowState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Explain the current or most recent optimization retained in this chat session."""
    used = _record_tool(state, "explain_schedule_changes")
    result = state.get("rescheduling_result") or state.get("last_rescheduling_result") or {}
    optimized = result.get("optimized_trains") or []
    if not optimized:
        explanation = {"summary": result.get("message", "No previous optimized schedule is available in this session."), "details": []}
    else:
        try:
            explanation = explain_optimization(
                baseline_trains=state.get("baseline_trains") or [],
                optimized_trains=optimized,
                remaining_conflicts=result.get("remaining_conflicts") or [],
            )
        except Exception as exc:
            logger.exception("Schedule explainability tool failed")
            explanation = {"summary": f"The schedule exists, but detailed explainability failed: {exc}", "details": []}
    return _tool_command(update={"explanation": explanation, "tools_used": used}, tool_call_id=tool_call_id, content=_json_text(explanation))


TRACKFLOW_TOOLS = [analyze_rail_traffic_tool, reschedule_after_track_closure_tool, explain_schedule_changes_tool]


SYSTEM_PROMPT = """You are TrackFlow, an AI railway traffic decision-support assistant.

Use the compact conversation memory and recent messages to understand follow-up
questions. Tool calculations are authoritative; never invent railway data.

TOOLS:
- analyze_rail_traffic: current synthetic network conflicts and hotspots.
- reschedule_after_track_closure: requires exact section_id, start_minute,
  end_minute; executes existing OR-Tools rescheduling and validation.
- explain_schedule_changes: explains the current or previous optimization in
  this same session.

RULES:
1. Answer general railway definitions directly; do not call tools unnecessarily.
2. For current network analysis or a delay-reduction plan, call analyze_rail_traffic.
3. A recommendation is not permission to change a schedule.
4. Only optimize when explicitly asked to optimize/reschedule/apply changes or
   simulate a specified disruption.
5. For a track closure, ask for missing section or time details; never guess.
6. After successful rescheduling, call explain_schedule_changes.
7. For follow-up questions about a previous optimization, use session memory and
   call explain_schedule_changes when needed. Do not rerun optimization unless asked.
8. If a tool fails, report it honestly. Never claim success after failure.
9. Distinguish recommendations from completed actions.
10. This synthetic prototype is not authorization for real railway operations.
"""


def _build_model_messages(state: TrackFlowState) -> list[BaseMessage]:
    """Construct a bounded prompt: summary + recent messages only."""
    history = list(state.get("messages") or [])
    recent = history[-MAX_RECENT_MESSAGES:]
    summary = (state.get("conversation_summary") or "").strip()
    system = SYSTEM_PROMPT
    if summary:
        system += "\n\nCOMPACT MEMORY FROM EARLIER TURNS (use as context, not as new tool output):\n" + summary[-MAX_MEMORY_CHARS:]
    compact_recent: list[BaseMessage] = []
    for message in recent:
        # Tool outputs are already compacted by _tool_command. Clip any legacy
        # oversized message that may have been saved by an older graph version.
        if isinstance(message, ToolMessage):
            compact_recent.append(ToolMessage(content=_clip(_message_text(message), MAX_TOOL_MESSAGE_CHARS), tool_call_id=message.tool_call_id))
        elif isinstance(message, HumanMessage):
            compact_recent.append(HumanMessage(content=_clip(_message_text(message), 1400), id=message.id))
        elif isinstance(message, AIMessage):
            # Preserve tool-call metadata when the message is a tool request.
            if getattr(message, "tool_calls", None):
                compact_recent.append(message)
            else:
                compact_recent.append(AIMessage(content=_clip(_message_text(message), 1200), id=message.id))
        else:
            compact_recent.append(message)
    return [SystemMessage(content=system), *compact_recent]


def agent_node(state: TrackFlowState) -> dict[str, Any]:
    try:
        response = get_groq_llm().bind_tools(TRACKFLOW_TOOLS).invoke(_build_model_messages(state))
        return {"messages": [response], "error": ""}
    except Exception as exc:
        logger.exception("Groq agent invocation failed")
        if "413" in str(exc) or "Request too large" in str(exc):
            message = (
                "The request still exceeded Groq's token limit after TrackFlow "
                "compacted the conversation. Please shorten this message or start "
                "a new chat; the previous session memory has not been deleted."
            )
        elif "429" in str(exc):
            message = "Groq rate limit reached. Please wait briefly and try again."
        else:
            message = "TrackFlow could not reach the language model. Check GROQ_API_KEY and the backend logs."
        return {"messages": [AIMessage(content=message)], "error": f"Groq agent unavailable: {exc}"}


def route_after_agent(state: TrackFlowState) -> str:
    if state.get("error"):
        return "final_response"
    messages = state.get("messages") or []
    last = messages[-1] if messages else None
    return "tools" if getattr(last, "tool_calls", None) else "final_response"


def _rolling_summary(existing: str, messages: list[BaseMessage], last_result: dict[str, Any] | None) -> str:
    """Extract a bounded, factual memory without spending another LLM call."""
    entries: list[str] = []
    if existing.strip():
        entries.append(existing.strip())
    for message in messages:
        if isinstance(message, HumanMessage):
            text = _message_text(message)
            if text:
                entries.append("Operator: " + _clip(text, 350))
        elif isinstance(message, AIMessage) and not getattr(message, "tool_calls", None):
            text = _message_text(message)
            if text and not text.startswith("Groq agent unavailable"):
                entries.append("TrackFlow: " + _clip(text, 450))
    if last_result:
        validation = last_result.get("validation") or {}
        entries.append(
            "Most recent optimization facts: " + _json_text({
                "status": last_result.get("status"),
                "total_added_departure_delay_minutes": last_result.get("total_added_departure_delay_minutes"),
                "remaining_conflict_count": len(last_result.get("remaining_conflicts") or []),
                "validation_passed": validation.get("passed", validation.get("is_valid")),
            })
        )
    # Keep a compact tail; this avoids an unbounded memory prompt.
    return "\n".join(entries)[-MAX_MEMORY_CHARS:]


def final_response_node(state: TrackFlowState) -> dict[str, Any]:
    messages = list(state.get("messages") or [])
    last_message = messages[-1] if messages else None
    tools_used = list(state.get("tools_used") or [])
    traffic = state.get("traffic_analysis") or {}
    result = state.get("rescheduling_result") or {}
    explanation = state.get("explanation") or {}
    explanation_was_run = "explain_schedule_changes" in tools_used
    rescheduling_was_run = "reschedule_after_track_closure" in tools_used

    # Direct answers do not need a second LLM call.
    if not tools_used:
        answer = _message_text(last_message) or state.get("error") or "I can answer railway questions, analyze the network, and help with defined rescheduling scenarios."
    else:
        if rescheduling_was_run or (explanation_was_run and (result or state.get("last_rescheduling_result"))):
            selected_result = result or state.get("last_rescheduling_result") or {}
            selected_disruptions = state.get("disruptions") or state.get("last_disruptions") or []
            fallback_state = {**state, "rescheduling_result": selected_result, "disruptions": selected_disruptions, "explanation": explanation or state.get("last_explanation") or {}}
            fallback = _optimization_fallback(fallback_state)
        elif traffic:
            fallback = _analysis_fallback(traffic)
        else:
            fallback = state.get("error") or "A tool ran but returned no usable result. Check the backend logs."

        compact_context = {
            "operator_request": state.get("user_request", ""),
            "tools_executed_this_turn": tools_used,
            "traffic_analysis": _compact_analysis(traffic) if traffic else {},
            "optimization": _compact_optimization(result) if result else {},
            "previous_optimization_for_follow_up": (
                _compact_optimization(state.get("last_rescheduling_result") or {})
                if explanation_was_run and not rescheduling_was_run else {}
            ),
            "disruptions": state.get("disruptions") or state.get("last_disruptions") or [],
            "explanation_summary": _clip(explanation.get("summary", ""), 900) if isinstance(explanation, dict) else "",
            "tool_error": state.get("error", ""),
        }
        prompt = (
            "Answer the operator's exact request using only this compact tool evidence. "
            "For a previous optimization follow-up, explicitly say it is the previous result. "
            "Report exact added departure delay when present. Do not claim a new optimization "
            "unless it ran this turn. Do not invent facts. Mention synthetic-model limitation.\n\n"
            "EVIDENCE:\n" + _json_text(compact_context)
        )
        try:
            response = get_groq_llm().invoke([
                SystemMessage(content="You are TrackFlow's concise results analyst. Use only supplied evidence."),
                HumanMessage(content=prompt),
            ])
            answer = _message_text(response) or fallback
        except Exception:
            logger.exception("Groq result summarization failed; using grounded fallback")
            answer = fallback

    # Add the final answer to memory, then prune old message objects. The
    # checkpointer retains compact summary + recent messages + exact last result.
    messages_with_answer = messages + [AIMessage(content=answer)]
    new_summary = _rolling_summary(
        state.get("conversation_summary", ""),
        ([next((m for m in reversed(messages) if isinstance(m, HumanMessage)), HumanMessage(content=state.get("user_request", ""))), AIMessage(content=answer)]),
        result or state.get("last_rescheduling_result"),
    )
    keep_ids = {m.id for m in messages_with_answer[-MAX_RECENT_MESSAGES:] if getattr(m, "id", None)}
    remove = [RemoveMessage(id=m.id) for m in messages if getattr(m, "id", None) and m.id not in keep_ids]

    updates: dict[str, Any] = {
        "final_response": answer,
        "conversation_summary": new_summary,
        "messages": [*remove, AIMessage(content=answer)],
    }
    if traffic:
        updates["last_traffic_analysis"] = traffic
    if result:
        updates["last_rescheduling_result"] = result
        updates["last_disruptions"] = state.get("disruptions") or []
    if explanation:
        updates["last_explanation"] = explanation
    return updates


_checkpointer = InMemorySaver()


def build_trackflow_graph(checkpointer=None):
    workflow = StateGraph(TrackFlowState)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", ToolNode(TRACKFLOW_TOOLS))
    workflow.add_node("final_response", final_response_node)
    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges("agent", route_after_agent, {"tools": "tools", "final_response": "final_response"})
    workflow.add_edge("tools", "agent")
    workflow.add_edge("final_response", END)
    return workflow.compile(checkpointer=checkpointer or _checkpointer)


trackflow_graph = build_trackflow_graph()
