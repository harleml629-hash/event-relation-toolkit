"""Transparent summaries and an explicitly illustrative linked-reply rule."""

from dataclasses import asdict
from bisect import bisect_left, bisect_right
import math

from .model import Policy, ValidationError


def interval_union_seconds(intervals):
    """Return the union length of half-open intervals; touching spans are continuous."""
    intervals = sorted(intervals)
    if not intervals:
        return 0.0
    start, end = intervals[0]
    total = 0.0
    for next_start, next_end in intervals[1:]:
        if next_start <= end:
            end = max(end, next_end)
        else:
            total += end - start
            start, end = next_start, next_end
    return total + end - start


def overlaps(a_start, a_end, b_start, b_end):
    return a_start < b_end and b_start < a_end


def linked_reply_candidates(session, policy):
    signals = [event for event in session.events if event.kind == "signal"]
    intervals = [event for event in session.events if event.kind == "interval"]
    replies = [event for event in session.events if event.kind == "reply"]

    overlapping_ids = set()
    furthest = None
    for signal in signals:
        if furthest is not None and signal.start < furthest.end:
            overlapping_ids.update((signal.event_id, furthest.event_id))
        if furthest is None or signal.end > furthest.end:
            furthest = signal

    interval_starts = [event.start for event in intervals]
    interval_max_ends = []
    for interval in intervals:
        prior = interval_max_ends[-1] if interval_max_ends else 0
        interval_max_ends.append(max(interval.end, prior))

    linked = {}
    for event in replies:
        if event.response_to is not None:
            linked.setdefault(event.response_to, []).append(event)

    direction = None
    run = []
    candidates = []
    previous_reply = None
    diagnostics = {
        "unlinked_replies": sum(event.response_to is None for event in replies),
        "signals_without_timely_reply": 0,
        "overlapping_signals_excluded": 0,
        "interval_interrupted_replies": 0,
        "nonchronological_replies_excluded": 0,
        "extra_linked_replies_not_counted": 0,
    }

    for signal in signals:
        if signal.event_id in overlapping_ids:
            diagnostics["overlapping_signals_excluded"] += 1
            direction, run, previous_reply = None, [], None
            continue
        replies_for_signal = [
            event for event in linked.get(signal.event_id, [])
            if event.start <= signal.end + policy.reply_window_seconds
        ]
        if not replies_for_signal:
            diagnostics["signals_without_timely_reply"] += 1
            direction, run, previous_reply = None, [], None
            continue
        reply = min(replies_for_signal, key=lambda event: (event.start, event.end, event.event_id))
        diagnostics["extra_linked_replies_not_counted"] += len(replies_for_signal) - 1
        if previous_reply is not None and reply.start <= previous_reply:
            diagnostics["nonchronological_replies_excluded"] += 1
            direction, run, previous_reply = None, [], None
            continue

        interval_index = bisect_right(interval_starts, reply.start) - 1
        if policy.reset_on_interval and interval_index >= 0 and interval_max_ends[interval_index] > signal.start:
            diagnostics["interval_interrupted_replies"] += 1
            direction, run, previous_reply = None, [], None
            continue
        if policy.reset_on_interval and previous_reply is not None:
            later_intervals = bisect_right(interval_starts, reply.start)
            earlier_intervals = bisect_left(interval_starts, previous_reply)
            if later_intervals > earlier_intervals:
                direction, run = None, []

        current_direction = (signal.actor, signal.recipient)
        if direction != current_direction:
            direction, run = current_direction, []
        run.append(signal.event_id)
        previous_reply = reply.start
        if len(run) == policy.required_replies:
            candidates.append({
                "source_entity": direction[0],
                "replying_entity": direction[1],
                "at_seconds": reply.start,
                "supporting_signal_ids": list(run),
                "interval_at_or_after_candidate": bool(
                    interval_max_ends and interval_max_ends[-1] > reply.start
                ),
            })
    return candidates, diagnostics


def analyze_session(session, policy):
    intervals = [event for event in session.events if event.kind == "interval"]
    counts = {
        entity: {"signals": 0, "replies": 0, "sole_interval_initiations": 0}
        for entity in session.entities
    }
    for event in session.events:
        if event.kind == "signal":
            counts[event.actor]["signals"] += 1
        elif event.kind == "reply":
            counts[event.actor]["replies"] += 1
        elif event.initiator in counts:
            counts[event.initiator]["sole_interval_initiations"] += 1

    union = interval_union_seconds((event.start, event.end) for event in intervals)
    candidates, diagnostics = linked_reply_candidates(session, policy)
    result = {
        "session_id": session.session_id,
        "observation_seconds": session.observation_seconds,
        "event_count": len(session.events),
        "entities": counts,
        "interval_event_count": len(intervals),
        "multiple_interval_initiations": sum(event.initiator == "multiple" for event in intervals),
        "unknown_interval_initiations": sum(event.initiator == "unknown" for event in intervals),
        "interval_annotated_seconds": sum(event.end - event.start for event in intervals),
        "interval_union_seconds": union,
        "interval_events_per_minute": len(intervals) * 60 / session.observation_seconds,
        "interval_time_fraction": union / session.observation_seconds,
        "linked_reply_candidates": candidates,
        "candidate_diagnostics": diagnostics,
    }
    if any(isinstance(value, float) and not math.isfinite(value) for value in result.values()):
        raise ValidationError("numeric range is too extreme to produce a finite summary")
    return result


def analyze(dataset, policy=None):
    policy = policy or Policy()
    return {
        "schema_version": 1,
        "synthetic": dataset.synthetic,
        "interpretation": "Generic event summaries and illustrative linked-reply candidates; no domain conclusion or prediction.",
        "policy": asdict(policy),
        "sessions": [analyze_session(session, policy) for session in dataset.sessions],
    }
