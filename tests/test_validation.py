from contextlib import redirect_stderr, redirect_stdout
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest

from event_relations.cli import main, load_json, write_json
from event_relations.analysis import analyze
from event_relations.demo import generate_demo
from event_relations.model import Policy, ValidationError, parse_dataset


class ValidationTests(unittest.TestCase):
    def reject(self, edit):
        raw = generate_demo()
        edit(raw)
        with self.assertRaises(ValidationError):
            parse_dataset(raw)

    def test_invalid_numeric_times(self):
        for value in (-1, float("nan"), float("inf"), True, "1", 10 ** 1000):
            with self.subTest(value_type=type(value).__name__):
                self.reject(lambda record: record["sessions"][0]["events"][0].update(start=value))

    def test_invalid_intervals(self):
        for start, end in ((2, 1), (2, 2), (0, 120)):
            with self.subTest(start=start, end=end):
                self.reject(lambda record: record["sessions"][0]["events"][0].update(start=start, end=end))

    def test_invalid_duration(self):
        self.reject(lambda record: record["sessions"][0].update(observation_seconds=0))

    def test_extreme_numeric_summary_is_rejected(self):
        raw = generate_demo()
        raw["sessions"] = raw["sessions"][:1]
        session = raw["sessions"][0]
        session["events"] = session["events"][-1:]
        session["observation_seconds"] = 1e-320
        session["events"][0].update(start=0, end=5e-321)
        with self.assertRaises(ValidationError):
            analyze(parse_dataset(raw))

    def test_duplicate_session_and_event(self):
        self.reject(lambda record: record["sessions"].append(copy.deepcopy(record["sessions"][0])))
        self.reject(lambda record: record["sessions"][0]["events"].append(copy.deepcopy(record["sessions"][0]["events"][0])))

    def test_identity_validation(self):
        self.reject(lambda record: record["sessions"][0].update(entities=["same", "same"]))
        self.reject(lambda record: record["sessions"][0].update(entities=["multiple", "other"]))
        self.reject(lambda record: record["sessions"][0]["events"][0].update(actor="not_an_entity"))
        self.reject(lambda record: record["sessions"][0]["events"][0].update(actor="entity_blue"))
        self.reject(lambda record: record["sessions"][0].update(session_id="bad/label"))

    def test_invalid_link(self):
        self.reject(lambda record: record["sessions"][0]["events"][1].update(response_to="missing"))
        self.reject(lambda record: record["sessions"][0]["events"][1].update(response_to="interval_later"))
        self.reject(lambda record: record["sessions"][0]["events"][1].update(start=1, end=2))
        self.reject(lambda record: record["sessions"][0]["events"][1].update(actor="entity_red", recipient="entity_blue"))

    def test_invalid_kinds_and_extra_fields(self):
        self.reject(lambda record: record.update(private_note="not_allowed"))
        self.reject(lambda record: record["sessions"][0]["events"][0].update(kind="other"))
        self.reject(lambda record: record["sessions"][0]["events"][0].update(initiator="entity_red"))
        self.reject(lambda record: record["sessions"][0]["events"][-1].update(actor="entity_red"))
        self.reject(lambda record: record["sessions"][0]["events"][-1].update(initiator="guess"))

    def test_version_and_synthetic_are_typed(self):
        self.reject(lambda record: record.update(schema_version=True))
        self.reject(lambda record: record.update(synthetic="true"))

    def test_invalid_policy(self):
        for values in (
            {"required_replies": True},
            {"required_replies": 1},
            {"required_replies": 4.5},
            {"reply_window_seconds": -1},
            {"reset_on_interval": "false"},
        ):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                Policy(**values)
        with self.assertRaises(ValidationError):
            Policy.parse({"required_replies": 4})

    def test_reject_duplicate_json_keys_and_nonfinite_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.json"
            for content in ('{"same":1,"same":2}', '{"value":NaN}'):
                path.write_text(content, encoding="utf-8")
                with self.assertRaises(ValidationError):
                    load_json(path)

    def test_cli_roundtrip_and_overwrite_refusal(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            source = Path(directory) / "demo.json"
            output = Path(directory) / "summary.json"
            self.assertEqual(main(["demo", "--output", str(source)]), 0)
            self.assertEqual(main(["validate", str(source)]), 0)
            self.assertEqual(main(["analyze", str(source), "--output", str(output)]), 0)
            before = output.read_bytes()
            self.assertEqual(main(["analyze", str(source), "--output", str(output)]), 2)
            self.assertEqual(output.read_bytes(), before)
            self.assertTrue(json.loads(before)["synthetic"])

    def test_cli_does_not_echo_private_path(self):
        error = io.StringIO()
        with redirect_stderr(error):
            self.assertEqual(main(["validate", "missing_private_filename.json"]), 2)
        self.assertNotIn("missing_private_filename", error.getvalue())

    def test_atomic_refusal_before_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "keep.json"
            path.write_text("keep", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                write_json(path, generate_demo())
            self.assertEqual(path.read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
