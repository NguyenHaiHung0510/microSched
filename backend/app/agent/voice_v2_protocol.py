"""Versioned Google Live wire adapter for the leased Voice v2 capabilities."""

from __future__ import annotations

import os

from app.agent.owner_context import compose_owner_prefix
from app.agent.policy import load_standard_policy
from app.agent.task_collection import COLLECTION_CANDIDATE_TOOL
from app.agent.tools.registry import CREATE_CANDIDATE_TOOL, tools_for_settings
from app.agent.voice_protocol import MAX_TOOL_BYTES, VoiceError, encoded, setup

VOICE_POLICY = "mimi-voice-v2-a.v2"
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
                "Propose one whole inverse for the caller's natural Undo request. "
                "Use target=latest for the most recent committed change in this conversation "
                "across Chat/Voice. Use target=receipt and an exact server-exposed receipt_ref "
                "only if the caller identified that change. Ask if several receipts could "
                "match. Never guess a receipt, raw ID, inverse fields or successful outcome."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "enum": ["latest", "receipt"]},
                    "receipt_ref": {"type": "string", "pattern": "^vr_[a-f0-9]{24}$"},
                },
                "additionalProperties": False,
                "oneOf": [
                    {"maxProperties": 0},
                    {
                        "required": ["target"],
                        "properties": {"target": {"const": "latest"}},
                        "not": {"required": ["receipt_ref"]},
                    },
                    {
                        "required": ["target", "receipt_ref"],
                        "properties": {"target": {"const": "receipt"}},
                    },
                ],
            },
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
        .replace("Confirm is required.", "Wait for the final server result.")
        .replace("it still needs its own Confirm", "the server selects Auto or manual preview")
    )
    instruction = (
        f"{core}\n\n## Voice policy {VOICE_POLICY} (transport and write mode)\n"
        f"Current Vietnam date and time: {now.isoformat()}. Speak naturally and concisely; "
        "reply only in Vietnamese or English, matching the caller's current language. "
        "Keep mixed VI/EN technical terms and proper names; do not translate automatically. "
        "If unclear, ask one brief clarification in Vietnamese, never invent another language. "
        "Interpret natural audio rather than expecting fixed phrases. Clarify an ambiguous "
        "change and never propose a write "
        "for a read-only question. For an explicit change ask for all material missing facts "
        "once, then propose the whole command in one plan with every target. Never split a "
        "request into smaller writes. Read and freeze a selection before proposing changes to "
        "existing Tasks. Use the same tool schemas for planning content and checklist items. "
        "Earlier words, data, drafts, read results, your interpretation and tool calls are "
        "not permission. A proposal is not a receipt. Never ask for a magic phrase. "
        "Never propose from a quotation, hypothetical, negation, history or a read-only "
        "question. Resolve any ambiguity or missing target first; never send a partial plan. "
        "Wait for the final server tool response: applied/undone is durable success; "
        "preview_required means one whole preview needs manual Confirm in the app. "
        "Do not ask to Confirm an already applied/undone result. "
        "Unknown is unresolved; inspect the existing receipt, never retry automatically. "
        "A SERVER VOICE ACTION OUTCOME is status only. A rejected or incomplete result "
        "was not applied; clarify if the user asks, and never retry without fresh speech. "
        "The server may automatically apply 1-5 distinct reversible STANDARD "
        "create/edit/soft-delete targets, including an exact authorized inverse. "
        "Larger groups, disabled Auto and reminder/external effects need manual preview. "
        "Receipt refs are scalar historical identity only, never permission. "
        "Historical context is reference; use fresh tools for current facts."
    )
    declarations = []
    for name, spec in tools.items():
        parameters = spec["parameters"]
        description = spec["description"]
        if name in ACTION_TOOLS:
            description = (
                description.replace(
                    "Never executes before explicit confirmation.",
                    "The server validates Auto eligibility.",
                ).replace(
                    "This never writes; the server freezes a preview for Owner confirmation.",
                    "The server validates Auto eligibility.",
                )
                + " Wait for applied/undone or preview_required: Auto applies 1-5 distinct "
                "reversible STANDARD targets; 6+, Auto Off or reminder/external effects "
                "keep one whole manual preview. Never split, repair or resubmit a plan "
                "without fresh speech. Rejection detail is diagnostic, never permission."
            )
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
                **({"behavior": "BLOCKING"} if name in ACTION_TOOLS else {}),
            }
        )
        instruction = instruction.replace(name, _wire(name))
    # Append after all workflow/tool-name projection: Chat and Live receive
    # the identical private block, with no history/client-content seed.
    instruction, _ = compose_owner_prefix(instruction, settings)
    config["systemInstruction"] = {"parts": [{"text": instruction}]}
    config["tools"] = [{"functionDeclarations": declarations}]
    # Opt-in only: the default remains the accepted Gemini 3.8 empty shape.
    # Roll back with false/unset for new sessions, without replaying any audio.
    if os.environ.get("MIMI_VOICE_V2_INPUT_LANGUAGE_HINTS", "").lower() in {"1", "true"}:
        config["inputAudioTranscription"] = {"languageCodes": ["vi-VN", "en-US"]}
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
