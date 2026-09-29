"""Strict validation for a small, generic event-record schema."""

from dataclasses import dataclass
import math


class ValidationError(ValueError):
    """The document does not satisfy the public event schema."""


def keys(value, required, context):
    if not isinstance(value, dict) or set(value) != set(required):
        raise ValidationError(f"{context}: fields must be exactly {', '.join(sorted(required))}")


def number(value, context, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{context}: expected a finite number")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite or value < 0 or (positive and value == 0):
        expectation = "positive" if positive else "nonnegative"
        raise ValidationError(f"{context}: expected a finite {expectation} number")
    return float(value)


def identifier(value, context):
    if not isinstance(value, str) or not value or len(value) > 80:
        raise ValidationError(f"{context}: expected a nonempty identifier of at most 80 characters")
    if not all(c.isascii() and (c.isalnum() or c in "_-") for c in value):
        raise ValidationError(f"{context}: identifiers allow ASCII letters, digits, underscores and hyphens only")
    return value


@dataclass(frozen=True)
class Event:
    event_id: str
    kind: str
    start: float
    end: float
    actor: str | None
    recipient: str | None
    initiator: str | None
    response_to: str | None


@dataclass(frozen=True)
class Session:
    session_id: str
    entities: tuple[str, str]
    observation_seconds: float
    events: tuple[Event, ...]


@dataclass(frozen=True)
class Dataset:
    synthetic: bool
    sessions: tuple[Session, ...]


@dataclass(frozen=True)
class Policy:
    required_replies: int = 4
    reply_window_seconds: float = 6.0
    reset_on_interval: bool = True

    def __post_init__(self):
        if type(self.required_replies) is not int or not 2 <= self.required_replies <= 100:
            raise ValidationError("required_replies: expected an integer from 2 to 100")
        number(self.reply_window_seconds, "reply_window_seconds")
        if type(self.reset_on_interval) is not bool:
            raise ValidationError("reset_on_interval: expected a boolean")

    @classmethod
    def parse(cls, value):
        keys(value, {"required_replies", "reply_window_seconds", "reset_on_interval"}, "policy")
        return cls(**value)


def parse_dataset(raw):
    keys(raw, {"schema_version", "synthetic", "sessions"}, "dataset")
    if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
        raise ValidationError("schema_version: only version 1 is supported")
    if type(raw["synthetic"]) is not bool:
        raise ValidationError("synthetic: expected a boolean; this label is not a privacy guarantee")
    if not isinstance(raw["sessions"], list) or not raw["sessions"]:
        raise ValidationError("sessions: expected a nonempty list")

    sessions = []
    seen_sessions = set()
    for index, item in enumerate(raw["sessions"]):
        context = f"session[{index}]"
        keys(item, {"session_id", "entities", "observation_seconds", "events"}, context)
        sid = identifier(item["session_id"], f"{context}.session_id")
        if sid in seen_sessions:
            raise ValidationError(f"{context}: duplicate session identifier")
        seen_sessions.add(sid)

        entities = item["entities"]
        if not isinstance(entities, list) or len(entities) != 2:
            raise ValidationError(f"{context}: exactly two entities are required")
        entities = tuple(identifier(entity, f"{context}.entity") for entity in entities)
        if entities[0] == entities[1] or set(entities) & {"multiple", "unknown"}:
            raise ValidationError(f"{context}: entities must differ and cannot use reserved identifiers")

        duration = number(item["observation_seconds"], f"{context}.observation_seconds", positive=True)
        if not isinstance(item["events"], list):
            raise ValidationError(f"{context}.events: expected a list")

        events = []
        seen_events = set()
        for event_index, record in enumerate(item["events"]):
            label = f"{context}.event[{event_index}]"
            required = {"event_id", "kind", "start", "end", "actor", "recipient", "initiator", "response_to"}
            keys(record, required, label)
            eid = identifier(record["event_id"], f"{label}.event_id")
            if eid in seen_events:
                raise ValidationError(f"{label}: duplicate event identifier")
            seen_events.add(eid)

            kind = record["kind"]
            if not isinstance(kind, str) or kind not in {"signal", "interval", "reply"}:
                raise ValidationError(f"{label}: unsupported event kind")
            start = number(record["start"], f"{label}.start")
            end = number(record["end"], f"{label}.end")
            if not start < end <= duration:
                raise ValidationError(f"{label}: require 0 <= start < end <= observation_seconds")

            actor, recipient = record["actor"], record["recipient"]
            initiator, response = record["initiator"], record["response_to"]
            if kind == "interval":
                if actor is not None or recipient is not None or response is not None:
                    raise ValidationError(f"{label}: interval actor, recipient and response_to must be null")
                if not isinstance(initiator, str) or initiator not in (*entities, "multiple", "unknown"):
                    raise ValidationError(f"{label}: invalid interval initiator")
            else:
                if actor not in entities or recipient not in entities or actor == recipient:
                    raise ValidationError(f"{label}: actor and recipient must be different session entities")
                if initiator is not None:
                    raise ValidationError(f"{label}: only intervals have an initiator")
                if kind == "signal" and response is not None:
                    raise ValidationError(f"{label}: signals cannot have response_to")
                if response is not None:
                    identifier(response, f"{label}.response_to")
            events.append(Event(eid, kind, start, end, actor, recipient, initiator, response))

        by_id = {event.event_id: event for event in events}
        for event in events:
            if event.response_to is None:
                continue
            signal = by_id.get(event.response_to)
            if signal is None or signal.kind != "signal":
                raise ValidationError(f"{context}: response_to must reference a signal in this session")
            if (signal.actor, signal.recipient) != (event.recipient, event.actor):
                raise ValidationError(f"{context}: linked reply direction does not match the signal")
            if event.start < signal.start:
                raise ValidationError(f"{context}: a reply cannot precede its signal")

        ordered = tuple(sorted(events, key=lambda event: (event.start, event.end, event.event_id)))
        sessions.append(Session(sid, entities, duration, ordered))
    return Dataset(raw["synthetic"], tuple(sessions))
