"""Procedural fixtures with no input files, fitted parameters, or network access."""


def event(event_id, kind, start, end, actor=None, recipient=None, initiator=None, response_to=None):
    return dict(
        event_id=event_id,
        kind=kind,
        start=start,
        end=end,
        actor=actor,
        recipient=recipient,
        initiator=initiator,
        response_to=response_to,
    )


def generate_demo():
    sessions = []
    for index, name in enumerate(("sample_arc", "sample_wave", "sample_dot")):
        events = []
        for number in range(4):
            start = 8.0 + number * 13.0
            signal_id = f"signal_{number + 1}"
            events.append(event(signal_id, "signal", start, start + 1.25, "entity_red", "entity_blue"))
            if index == 1 and number == 3:
                events[-1]["actor"], events[-1]["recipient"] = "entity_blue", "entity_red"
            actor, recipient = events[-1]["recipient"], events[-1]["actor"]
            events.append(event(
                f"reply_{number + 1}",
                "reply",
                start + 2,
                start + 2.75,
                actor,
                recipient,
                response_to=signal_id,
            ))
        if index == 0:
            events.append(event("interval_later", "interval", 70, 73, initiator="entity_red"))
        elif index == 1:
            events.append(event("interval_early", "interval", 1, 3.5, initiator="multiple"))
            events.append(event("interval_unknown", "interval", 2.5, 4.0, initiator="unknown"))
        else:
            events.append(event("interval_between", "interval", 26, 28, initiator="entity_blue"))
        sessions.append({
            "session_id": name,
            "entities": ["entity_red", "entity_blue"],
            "observation_seconds": 96.0,
            "events": events,
        })
    return {"schema_version": 1, "synthetic": True, "sessions": sessions}
