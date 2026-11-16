"""Versioned Google Live wire adapter for the leased Voice v2 capabilities."""

from __future__ import annotations

from app.agent.owner_context import compose_owner_prefix
from app.agent.policy import load_standard_policy
from app.agent.task_collection import COLLECTION_CANDIDATE_TOOL
from app.agent.tools.registry import CREATE_CANDIDATE_TOOL, tools_for_settings
from app.agent.voice_protocol import MAX_TOOL_BYTES, VoiceError, encoded, setup

VOICE_POLICY = "mimi-voice-v2-a.v1"
UNDO_TOOL = "voice.undo_latest.v1"
ACTION_TOOLS = frozenset({CREATE_CANDIDATE_TOOL, COLLECTION_CANDIDATE_TOOL, UNDO_TOOL})


def _wire(name):
    return name.replace(".", "_")


def v2_tools(settings):
    tools = {t["function"]["name"]: t["function"] for t in tools_for_settings(settings)}
    if settings.mimi_collection_enabled:
        tools[UNDO_TOOL] = {
            "name": UNDO_TOOL,
            "description": (
                "Propose Undo only for an explicit request about the latest Voice apply. "
                "The server selects and checks the receipt. Do not supply an ID or claim success."
            ),
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        }
    return tools


def setup_v2(now, settings):
    config = setup(now)["setup"]
    tools = v2_tools(settings)
    shared = load_standard_policy(
        collection_enabled=settings.mimi_collection_enabled,
        calendar_enabled=settings.mimi_calendar_read_enabled,
    )
    # Keep the common business rules; the dialogue/confirmation transport
    # differs from Chat. Replace the Chat-only workflow and tool-loop text.
    core, _, tail = shared.text.partition("## Workflow and confirmation")
    _, _, workflow_tail = tail.partition("## Evidence gaps and limits")
    marker = (
        "## Collection capability and coverage"
        if settings.mimi_collection_enabled
        else "## Single-create capability"
    )
    start = workflow_tail.find(marker)
    if start >= 0:
        core += workflow_tail[start:]
    core = (
        core.replace("take id from the server authority's reserved_task_id", "omit id")
        .replace("use the server authority's reserved_task_id for id, ", "")
        .replace("for review and confirmation", "for server validation")
    )
    instruction = (
        f"{core}\n\n## Voice policy {VOICE_POLICY} (transport and write mode)\n"
        f"Current Vietnam date and time: {now.isoformat()}. Speak naturally and concisely; "
        "follow the caller's language. Clarify an ambiguous change and never propose a write "
        "for a read-only question. For an explicit change ask for all material missing facts "
        "once, then propose the whole command in one plan with every target. Never split a "
        "request into smaller writes. Read and freeze a selection before proposing changes to "
        "existing Tasks. Use the same tool schemas for planning content and checklist items. "
        "Earlier words, data, drafts, read results, your interpretation and tool calls are "
        "not permission. A proposal is not a receipt. Say that a proposal needs checking "
        "in the app; never say it has run from a staged acknowledgment, even for Undo. "
        "The app displays the actual apply/preview outcome after the completed turn. "
        "A SERVER VOICE ACTION OUTCOME is status only. A rejected or incomplete result "
        "was not applied; clarify if the user asks, and never retry without fresh speech. "
        "Deletion, restore, notifications, and other external effects require manual review. "
        "Historical context is reference; use fresh tools for current facts."
    )
    declarations = []
    for name, spec in tools.items():
        parameters = spec["parameters"]
        description = spec["description"]
        if name == CREATE_CANDIDATE_TOOL:
            task = parameters["properties"]["task"]
            parameters = {
                **parameters,
                "properties": {
                    "task": {
                        **task,
                        "properties": {k: v for k, v in task["properties"].items() if k != "id"},
                        "required": [k for k in task["required"] if k != "id"],
                    },
                },
            }
            description = description.replace(
                ", and take id from the server authority's reserved_task_id", "; omit id"
            )
        # Live names allow underscores, not the version separators in Chat.
        declarations.append(
            {
                "name": _wire(name),
                "description": description,
                "parametersJsonSchema": parameters,
            }
        )
        instruction = instruction.replace(name, _wire(name))
    # Append after all workflow/tool-name projection: Chat and Live receive
    # the identical private block, with no history/client-content seed.
    instruction, _ = compose_owner_prefix(instruction, settings)
    config["systemInstruction"] = {"parts": [{"text": instruction}]}
    config["tools"] = [{"functionDeclarations": declarations}]
    # Keep the conversational Live transcription setup from V1. The wire
    # transcript's utterance offsets are optional; word timestamps are not used.
    config["sessionResumption"] = {}
    if settings.mimi_voice_v2_compression_enabled:
        config["contextWindowCompression"] = {
            "triggerTokens": "25000",
            "slidingWindow": {"targetTokens": "8000"},
        }
    return {"setup": config}


def v2_tool_request(call, settings):
    if not isinstance(call, dict) or set(call) - {"id", "name", "args"}:
        raise VoiceError("voice_tool_invalid")
    identity, wire, arguments = call.get("id"), call.get("name"), call.get("args", {})
    names = {_wire(name): name for name in v2_tools(settings)}
    if (
        not isinstance(identity, str)
        or not 1 <= len(identity) <= 160
        or not isinstance(wire, str)
        or wire not in names
        or not isinstance(arguments, dict)
        or len(encoded(arguments).encode()) > MAX_TOOL_BYTES
    ):
        raise VoiceError("voice_tool_not_allowed")
    return identity, wire, names[wire], arguments
