# Methods and data contract

## Scope

This package consumes generic event records involving two entities. It does not
infer events, calibrate thresholds, assess source quality, or validate an
application-specific interpretation. The rules are deterministic software examples.
No private counts, durations, identities, source shapes, fitted parameters, or
derived statistics are used to construct the bundled synthetic fixtures.

## JSON contract, version 1

The root contains exactly `schema_version` (integer 1), `synthetic` (boolean),
and `sessions` (nonempty list). The author supplies `synthetic`; setting it to true
does not make real records safe to publish.

Every session contains exactly:

| Field | Meaning |
| --- | --- |
| `session_id` | Unique session label within this document |
| `entities` | Two different labels; `multiple` and `unknown` are reserved |
| `observation_seconds` | Finite positive session length, in seconds |
| `events` | List of event objects; an empty list is allowed |

Every event contains exactly:

| Field | Meaning |
| --- | --- |
| `event_id` | Unique label within the session |
| `kind` | `signal`, `interval`, or `reply` |
| `start`, `end` | Finite times: `0 <= start < end <= observation_seconds` |
| `actor`, `recipient` | Different session entities for signals/replies; null for intervals |
| `initiator` | One entity, `multiple`, or `unknown` for intervals; null otherwise |
| `response_to` | A signal identifier for a linked reply, or null |

Identifiers use ASCII letters, digits, underscores and hyphens, up to 80
characters. Unknown fields, duplicate identifiers, duplicate JSON object keys,
invalid types, nonfinite numbers, and events outside the session window are
rejected. Records are sorted by time internally; input order is not significant.
A linked reply must reference a signal in the same session, reverse its direction,
and not start before that signal begins. Unlinked replies are accepted and counted,
but cannot support a linked-reply candidate.

The CLI reads at most 16 MiB per input document. Existing output files are not
overwritten. Extreme numeric inputs that cannot produce finite summary values are
rejected. Errors do not intentionally echo source values or local paths.

## Counts, durations, and denominators

- One interval record contributes one interval event. The program does not split
  or merge event counts.
- Sole initiations are counted per entity. `multiple` initiations are counted
  once in their own category, not added to either entity's sole count. `unknown`
  initiations remain unknown. These four categories sum to the interval count.
- `interval_annotated_seconds` sums every interval length, counting overlaps more
  than once in this descriptive record total.
- `interval_union_seconds` measures the union of half-open intervals. It removes
  overlapping time without changing event counts.
- `interval_events_per_minute = interval_event_count * 60 / observation_seconds`.
- `interval_time_fraction = interval_union_seconds / observation_seconds`.

No durations are rounded before calculation. JSON uses ordinary binary floating
point numbers. Use suitable tolerances when checking decimal times independently.
There is no pooled conclusion across sessions.

## Illustrative linked-reply sequence

The policy fields are `required_replies` (integer 2 through 100),
`reply_window_seconds` (finite nonnegative number), and `reset_on_interval`
(boolean). The demonstration values are four replies, a six-second window after
the signal ends, and reset enabled. They are arbitrary constants, not learned or
validated values.

1. Examine signals in chronological order. Overlapping signals are excluded from
   sequence construction and reset the sequence.
2. Select the earliest explicitly linked reply starting no later than
   `signal.end + reply_window_seconds`. Ties use reply end and then event ID.
   Multiple eligible replies to one signal supply at most one reply. No timely
   reply resets the sequence.
3. Selected reply start times must increase. A non-increasing reply resets the
   sequence and is excluded.
4. With `reset_on_interval=true`, an interval active between a signal start and
   its reply start makes that opportunity ineligible. An interval starting
   between successive reply starts resets the preceding sequence. An interval
   starting exactly at a reply time interrupts it. An interval ending exactly
   at the next signal start does not overlap that signal, but its intervening
   start can still reset the preceding sequence.
5. A change in signal direction begins a new run. Unlinked replies do not
   establish a direction. Only explicitly linked eligible opportunities count.
6. Emit one candidate when a run first reaches `required_replies`. A longer
   uninterrupted run does not emit overlapping duplicate candidates; a later
   reset may permit another candidate.
7. Flag any interval active at or after the candidate time. This is descriptive
   and has no application-specific interpretation.

Each candidate contains `source_entity`, `replying_entity`, `at_seconds`,
`supporting_signal_ids`, and `interval_at_or_after_candidate`. The candidate time
is the start of the threshold-reaching reply. The selected policy and diagnostic
counts are included in each summary.

With reset disabled, intervals do not exclude or reset replies; the descriptive
interval flag remains. Unanswered signals and direction reversals still reset
sequences. A declared link is an input relationship, not proof of causality. These
software rules do not establish that separate records represent independent
real-world events or that a detected sequence predicts anything.

## Synthetic fixture and complexity

The generator uses constant event templates and simple arithmetic without file
inputs, randomness, noise fitted to observations, or model weights. It exercises
code branches rather than reproducing a real source or its distribution.

Input sorting, interval union, and binary-search interval checks use approximately
`O(E log E)` time and `O(E)` memory per session, where E is event count. No measured
real-world speed or predictive accuracy is claimed.
