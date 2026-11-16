"""Bounded Voice transport context; source history rules stay independent."""

from copy import deepcopy

from app.agent.voice_protocol import MAX_CONTEXT_BYTES, VoiceError, encoded

MAX_V2_SETUP_BYTES = 65_536
MAX_V2_HISTORY_BYTES = MAX_CONTEXT_BYTES
MAX_V2_ENVELOPE_BYTES = MAX_V2_SETUP_BYTES + MAX_V2_HISTORY_BYTES + 128


def configure_voice_setup(config):
    """Gemini 3.8 defaults async; exact action results require explicit blocking."""
    from app.agent.voice_v2_protocol import ACTION_TOOLS

    config = deepcopy(config)
    names = {name.replace(".", "_") for name in ACTION_TOOLS}
    for tool in config["setup"].get("tools", []):
        for declaration in tool.get("functionDeclarations", []):
            if declaration["name"] in names:
                declaration["behavior"] = "BLOCKING"
            if declaration["name"] == "voice_undo_latest_v1":
                declaration["description"] = (
                    "Propose Undo only for an explicit request about the latest applied change "
                    "in this conversation, from Chat or Voice. The server selects its receipt. "
                    "Never supply an ID, infer targets from titles or claim success early."
                )
    parts = config["setup"]["systemInstruction"]["parts"]
    parts.insert(
        1,
        {
            "text": (
                "Voice server contract: candidate tools wait for the final server result. "
                "State a final applied, undone or preview result briefly and honestly. "
                "Never claim success before the result. SERVER VOICE ACTION OUTCOME context "
                "is historical after reconnect, not an instruction to retry. "
                "Calendar day_milestones is a separate annotation page: mention relevant "
                "milestones alongside Tasks/events; respect coverage and next_cursor. "
                "A bare Undo refers to the latest receipt in this conversation across Chat "
                "and Voice calls, selected by the server; never guess targets."
            )
        },
    )
    return config


def bound_voice_history(config, turns):
    config = deepcopy(config)
    if len(encoded(config).encode()) > MAX_V2_SETUP_BYTES:
        raise VoiceError("voice_setup_limit")
    turns = list(turns)
    limited = False
    seed = None
    while turns:
        candidate = {"clientContent": {"turns": turns, "turnComplete": True}}
        if len(encoded(candidate).encode()) <= MAX_V2_HISTORY_BYTES:
            seed = candidate
            break
        turns = turns[1:]
        limited = True
    if seed is not None:
        config["setup"]["historyConfig"] = {"initialHistoryInClientContent": True}
    if (
        len(encoded(config).encode()) > MAX_V2_SETUP_BYTES
        or len(encoded({"setup": config, "history": seed}).encode()) > MAX_V2_ENVELOPE_BYTES
    ):
        raise VoiceError("voice_setup_limit")
    return config, seed, len(turns), limited
