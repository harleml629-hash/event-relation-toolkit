# Event Relation Toolkit

Offline summaries of generic event records involving two entities.

[简体中文](README.zh-CN.md) · [Methods](docs/METHODS.md) · [Privacy](docs/PRIVACY.md) · [Publishing](docs/PUBLISHING.md) · [Contributing](CONTRIBUTING.md)

This independently written software example includes only procedural synthetic
fixtures. No private records, derived values, fitted parameters, model weights, or
inherited Git history are included. Labels and examples have no application-specific
meaning.

## Capabilities

- Validate entity labels, times, event kinds, and explicit signal-to-reply links.
- Count signals, replies, and interval initiation categories.
- Report summed interval lengths and overlap-corrected interval time.
- Find illustrative linked-reply sequences under an explicit configuration.
- Produce deterministic JSON locally, without telemetry or external services.
- Build an allowlisted text-only release and verify it before isolated preparation.

The toolkit consumes event records already supplied by the user. It does not infer
events from media, train models, anonymize records, or validate a real-world
interpretation. A candidate is a software pattern, with no prediction or accuracy
claim. Neutral names reduce application-specific disclosure; the public algorithm
and account activity can still reveal information about the publisher.

## Quick start

Requires Python 3.11 or later. Run from this directory. The demonstration, tests,
and release tools use only the Python standard library; no installation or network
connection is needed.

```sh
python -B -m event_relations validate examples/synthetic_events.json
mkdir ../event-demo-output
python -B -m event_relations demo --output ../event-demo-output/demo.json
python -B -m event_relations analyze ../event-demo-output/demo.json --policy settings.demo.json --output ../event-demo-output/summary.json
python -B -m unittest discover -s tests -v
```

If the output directory already exists, skip `mkdir`. Existing output files are
never overwritten; choose new filenames for another run. Keep output outside this
release source tree. `private_data` and `local_runs` are forbidden anywhere inside
that tree, including empty directories and case variants. `-B` prevents Python
bytecode caches. Some systems name the executable `python3`.

The [expected summary](examples/expected_summary.json) corresponds to the bundled
synthetic fixture. Its scenarios exercise direction changes, interval interruption,
overlap, initiation categories, and intervals following a candidate. These are
software test cases, not observations of a real system.

## Environment and input

Runtime dependencies: none. Packaging metadata is in `pyproject.toml`. An optional
`python -m venv .venv` creates an isolated environment. Optional installation with
`python -m pip install .` provides the `event-relations` command, but that packaging
step may download its declared build tool.

Times are seconds relative to each session's own start. Each session has two
different entity labels. The event kinds are `signal`, `reply`, and `interval`.
A reply may explicitly reference a signal using `response_to`; nearby timestamps
alone never create a link. The constants in `settings.demo.json` are arbitrary
software examples. See [Methods](docs/METHODS.md) for the complete contract.

## Prepare a release

```sh
python -B tools/build_release.py --check
python -B tools/build_release.py --output ../event-relation-toolkit-public.zip
```

The builder stops if forbidden local-data names occur anywhere in the source
tree, even inside excluded directories. Unexpected files outside the documented
excluded directories also stop the build. It verifies the synthetic fixture and
expected summary, and creates a ZIP with per-file hashes and fixed metadata.

Publish only a reviewed archive unpacked to a new directory outside the entire
private workspace. The [publishing procedure](docs/PUBLISHING.md) uses
`tools/prepare_public_repo.py` to verify the archive hash, manifest, allowlist, and
destination before extraction. Create fresh Git history there and stage only the
manifest-listed files plus the manifest. The preparation tool does not initialize
Git or upload anything.

Public questions and contributions must follow [CONTRIBUTING.md](CONTRIBUTING.md).
Only invented minimal examples are allowed; private data and private-derived
content must never be placed in public text or attachments.

## License

No public-use license has been selected. See [LICENSE_NOTICE.md](LICENSE_NOTICE.md).
