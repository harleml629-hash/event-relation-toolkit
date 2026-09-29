import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from event_relations.analysis import analyze, interval_union_seconds, overlaps
from event_relations.demo import event, generate_demo
from event_relations.model import Policy, parse_dataset

ROOT = Path(__file__).resolve().parents[1]


def summary(raw, policy=None):
    return analyze(parse_dataset(raw), policy)["sessions"][0]


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.raw = generate_demo()
        self.raw["sessions"] = self.raw["sessions"][:1]
        self.raw["sessions"][0]["events"] = [
            item for item in self.raw["sessions"][0]["events"] if item["kind"] != "interval"
        ]

    def test_interval_union(self):
        self.assertEqual(interval_union_seconds([(1, 5), (2, 3), (4, 8), (8, 9), (12, 13)]), 9)
        self.assertEqual(interval_union_seconds([]), 0)
        self.assertFalse(overlaps(0, 1, 1, 2))

    def test_fixture_matches_generator(self):
        fixture = json.loads((ROOT / "examples/synthetic_events.json").read_text())
        self.assertEqual(fixture, generate_demo())

    def test_generator_and_analysis_do_not_need_files_or_network(self):
        with patch("builtins.open", side_effect=AssertionError("file access forbidden")), \
                patch("pathlib.Path.open", side_effect=AssertionError("file access forbidden")), \
                patch("socket.socket", side_effect=AssertionError("network access forbidden")):
            first = analyze(parse_dataset(generate_demo()))
            second = analyze(parse_dataset(generate_demo()))
        self.assertEqual(first, second)

    def test_interval_union_against_independent_discrete_reference(self):
        intervals = [(a, b) for a in range(6) for b in range(a + 1, 7)]
        for first in intervals:
            for second in intervals:
                expected = len(set(range(*first)) | set(range(*second)))
                self.assertEqual(interval_union_seconds([first, second]), expected)

    def test_expected_summary_matches(self):
        expected = json.loads((ROOT / "examples/expected_summary.json").read_text())
        self.assertEqual(analyze(parse_dataset(generate_demo())), expected)

    def test_independent_hand_calculation(self):
        results = analyze(parse_dataset(generate_demo()))["sessions"]
        self.assertEqual([len(item["linked_reply_candidates"]) for item in results], [1, 0, 0])
        self.assertEqual(results[0]["linked_reply_candidates"][0]["at_seconds"], 49)
        self.assertTrue(results[0]["linked_reply_candidates"][0]["interval_at_or_after_candidate"])
        self.assertEqual(results[1]["interval_annotated_seconds"], 4)
        self.assertEqual(results[1]["interval_union_seconds"], 3)
        self.assertEqual(results[1]["multiple_interval_initiations"], 1)
        self.assertEqual(results[1]["unknown_interval_initiations"], 1)
        self.assertEqual(results[1]["interval_events_per_minute"], 1.25)
        self.assertEqual(results[1]["interval_time_fraction"], 3 / 96)

    def test_initiator_counts_reconcile(self):
        for record in analyze(parse_dataset(generate_demo()))["sessions"]:
            sole = sum(item["sole_interval_initiations"] for item in record["entities"].values())
            total = sole + record["multiple_interval_initiations"] + record["unknown_interval_initiations"]
            self.assertEqual(total, record["interval_event_count"])
            self.assertLessEqual(record["interval_union_seconds"], record["observation_seconds"])

    def test_sequence_without_later_interval(self):
        candidate = summary(self.raw)["linked_reply_candidates"][0]
        self.assertFalse(candidate["interval_at_or_after_candidate"])
        self.assertEqual(len(candidate["supporting_signal_ids"]), 4)

    def test_input_order_does_not_matter(self):
        other = copy.deepcopy(self.raw)
        other["sessions"][0]["events"].reverse()
        self.assertEqual(summary(other), summary(self.raw))

    def test_empty_events(self):
        self.raw["sessions"][0]["events"] = []
        result = summary(self.raw)
        self.assertEqual(result["interval_union_seconds"], 0)
        self.assertEqual(result["linked_reply_candidates"], [])

    def test_missing_reply_resets(self):
        self.raw["sessions"][0]["events"] = [
            item for item in self.raw["sessions"][0]["events"] if item["event_id"] != "reply_2"
        ]
        result = summary(self.raw)
        self.assertEqual(result["linked_reply_candidates"], [])
        self.assertEqual(result["candidate_diagnostics"]["signals_without_timely_reply"], 1)

    def test_duplicate_reply_is_not_an_extra_opportunity(self):
        duplicate = copy.deepcopy(self.raw["sessions"][0]["events"][1])
        duplicate.update(event_id="extra_reply", start=10.5, end=11.0)
        self.raw["sessions"][0]["events"].append(duplicate)
        result = summary(self.raw)
        self.assertEqual(result["candidate_diagnostics"]["extra_linked_replies_not_counted"], 1)
        self.assertEqual(result["linked_reply_candidates"][0]["at_seconds"], 49)

    def test_unlinked_reply_is_not_inferred(self):
        self.raw["sessions"][0]["events"][1]["response_to"] = None
        result = summary(self.raw)
        self.assertEqual(result["linked_reply_candidates"], [])
        self.assertEqual(result["candidate_diagnostics"]["unlinked_replies"], 1)

    def test_window_boundary(self):
        reply = self.raw["sessions"][0]["events"][1]
        reply.update(start=15.25, end=15.5)
        self.assertEqual(len(summary(self.raw)["linked_reply_candidates"]), 1)
        reply.update(start=15.2501, end=15.5)
        self.assertEqual(summary(self.raw)["linked_reply_candidates"], [])

    def test_overlapping_signals_are_excluded(self):
        self.raw["sessions"][0]["events"].append(event("overlap", "signal", 8.5, 9, "entity_red", "entity_blue"))
        result = summary(self.raw)
        self.assertEqual(result["linked_reply_candidates"], [])
        self.assertEqual(result["candidate_diagnostics"]["overlapping_signals_excluded"], 2)

    def test_nested_signals_all_excluded(self):
        self.raw["sessions"][0]["events"][0]["end"] = 80
        result = summary(self.raw)
        self.assertEqual(result["candidate_diagnostics"]["overlapping_signals_excluded"], 4)

    def test_interval_interrupts_but_relaxed_policy_is_explicit(self):
        self.raw["sessions"][0]["events"].append(event("interrupt", "interval", 22, 24, initiator="multiple"))
        self.assertEqual(summary(self.raw)["linked_reply_candidates"], [])
        relaxed = summary(self.raw, Policy(reset_on_interval=False))
        self.assertEqual(len(relaxed["linked_reply_candidates"]), 1)

    def test_interval_exactly_at_reply_interrupts(self):
        self.raw["sessions"][0]["events"].append(event("tie", "interval", 23, 23.5, initiator="unknown"))
        result = summary(self.raw)
        self.assertEqual(result["candidate_diagnostics"]["interval_interrupted_replies"], 1)

    def test_interval_ending_at_signal_resets_previous_run(self):
        self.raw["sessions"][0]["events"].append(event("boundary", "interval", 19, 21, initiator="unknown"))
        result = summary(self.raw)
        self.assertEqual(result["linked_reply_candidates"], [])
        self.assertEqual(result["candidate_diagnostics"]["interval_interrupted_replies"], 0)

    def test_threshold_not_emitted_repeatedly(self):
        result = summary(self.raw, Policy(required_replies=2))
        self.assertEqual(len(result["linked_reply_candidates"]), 1)
        self.assertEqual(result["linked_reply_candidates"][0]["at_seconds"], 23)

    def test_reversed_direction_starts_new_run(self):
        raw = generate_demo()
        raw["sessions"] = raw["sessions"][1:2]
        self.assertEqual(summary(raw)["linked_reply_candidates"], [])

    def test_independent_sessions_do_not_join_sequences(self):
        self.raw["sessions"][0]["events"] = self.raw["sessions"][0]["events"][:4]
        second = copy.deepcopy(self.raw["sessions"][0])
        second["session_id"] = "separate"
        self.raw["sessions"].append(second)
        summaries = analyze(parse_dataset(self.raw))["sessions"]
        self.assertTrue(all(not item["linked_reply_candidates"] for item in summaries))


if __name__ == "__main__":
    unittest.main()
