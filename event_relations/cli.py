"""Offline command line interface. Existing output files are never overwritten."""

import argparse
import json
from pathlib import Path
import sys

from .analysis import analyze
from .demo import generate_demo
from .model import Policy, ValidationError, parse_dataset

MAX_INPUT_BYTES = 16 * 1024 * 1024


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValidationError("JSON contains a duplicate object key")
        value[key] = item
    return value


def load_json(path):
    with Path(path).open("rb") as stream:
        data = stream.read(MAX_INPUT_BYTES + 1)
    if len(data) > MAX_INPUT_BYTES:
        raise ValidationError("input exceeds the documented 16 MiB limit")
    return json.loads(data.decode("utf-8-sig"), object_pairs_hook=unique_object,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValidationError("nonfinite JSON number")))


def write_json(path, value):
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    # Exclusive creation also refuses existing symlinks. Parents must already exist.
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline generic event-relation toolkit")
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="generate independent, synthetic fixtures")
    demo.add_argument("--output", type=Path, required=True)
    validate = commands.add_parser("validate", help="validate one annotation document")
    validate.add_argument("input", type=Path)
    summary = commands.add_parser("analyze", help="summarize explicit event records")
    summary.add_argument("input", type=Path)
    summary.add_argument("--policy", type=Path)
    summary.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            write_json(args.output, generate_demo())
            print("Synthetic example created; no source dataset was read.")
        else:
            dataset = parse_dataset(load_json(args.input))
            if args.command == "validate":
                print(f"Valid document: {len(dataset.sessions)} sessions.")
            else:
                policy = Policy.parse(load_json(args.policy)) if args.policy else Policy()
                write_json(args.output, analyze(dataset, policy))
                print("Summary created. Candidate patterns are illustrative and domain-neutral.")
        return 0
    except (ValueError, UnicodeError) as exc:
        # Do not echo input content or local file paths in errors.
        print(f"Invalid input: {exc}" if isinstance(exc, ValidationError) else "Invalid JSON encoding or syntax.", file=sys.stderr)
    except FileExistsError:
        print("Output already exists. Choose a new output filename.", file=sys.stderr)
    except OSError:
        print("File operation failed. Check paths, parent directories and permissions.", file=sys.stderr)
    except RecursionError:
        print("Input nesting is too deep.", file=sys.stderr)
    return 2
