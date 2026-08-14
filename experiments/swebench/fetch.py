#!/usr/bin/env python3
"""T3.1: fetch the pinned upstream artifacts and derive Experiment 1's label table.

**Nothing upstream is redistributed.** Under `docs/DECISIONS.md` D1.4 this repo ships a
deterministic fetch-and-derive pipeline plus checksums of what it must produce. Derived files go
to `derived/` and are untracked; what is committed is this script, the digests of every upstream
file consumed, the expected checksums of the derived files, and de minimis aggregates.

**The committed manifest is an input, not an output.** A normal run compares every digest it
observes against `manifests/upstream_digests.json` and stops on any mismatch. Writing that file
requires `--bootstrap`, because a fetcher that overwrites its own expected checksums with whatever
it just saw cannot detect upstream moving: it would exit zero and quietly redefine "expected".

**Gate 0 comes before parsing.** The published board is fetched whole and its raw bytes verified
against the digest recorded in `docs/recon_swebench.md`. The pre-registration defines adjacency by
the array order in that exact file, and the coverage rule needs entries below rank 20 if a
substitution fires, so the file is the input rather than a summary of it.

Gates 1 to 4 are the pre-registration's integrity gates and run before anything is written.

Network access is required, which is the trade D1.4 records: no offline reproduction, in exchange
for redistributing nothing and failing loudly when upstream moves.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
DERIVED = HERE / "derived"
MANIFESTS = HERE / "manifests"
MANIFEST_PATH = MANIFESTS / "upstream_digests.json"

# Pinned in docs/recon_swebench.md. Changing any of these changes what "the board" and "the
# artifacts" mean, and every committed checksum becomes stale.
BOARD_COMMIT = "7c4289f30aa1a1c63c2e2a25aae30c16d92b5114"
BOARD_URL = (
    "https://raw.githubusercontent.com/SWE-bench/swe-bench.github.io/"
    f"{BOARD_COMMIT}/data/leaderboards.json"
)
BOARD_SHA256 = "c3bf3a74d7d67ba7e2777e197f96894601917e8e186a078133897ed3e81566e5"

ARTIFACT_COMMIT = "2f15350cd32becc4569e0d826361048555b605c0"
ARTIFACT_BASE = (
    f"https://raw.githubusercontent.com/SWE-bench/experiments/{ARTIFACT_COMMIT}/evaluation"
)

DATASET_REVISION = "c104f840cc67f8b6eec6f759ebc8b2693d585d4a"
DATASET_URL = (
    "https://huggingface.co/datasets/princeton-nlp/SWE-bench_Verified/resolve/"
    f"{DATASET_REVISION}/data/test-00000-of-00001.parquet"
)

BOARD_NAME = "Verified"
N_TOP = 20
INSTRUMENT = "hidden-tests"
EXPECTED_INSTANCES = 500

FORMAT_RESOLVED_LIST = "resolved-id-list"
FORMAT_INSTANCE_MAP = "per-instance-map"

LABEL_COLUMNS = ("item_id", "system", "run", "instrument", "label")


class GateFailure(RuntimeError):
    """An integrity gate did not hold. The run stops rather than reporting around it."""


@dataclass
class Entry:
    """One leaderboard entry, in published order."""

    rank: int
    folder: str
    published_rate: float
    checked: object
    date: str

    def __post_init__(self) -> None:
        if self.rank < 1:
            raise ValueError(f"rank must be at least 1, got {self.rank}")
        if not isinstance(self.folder, str):
            raise ValueError(f"folder must be a string, got {self.folder!r}")
        if not 0.0 <= self.published_rate <= 100.0:
            raise ValueError(
                f"published_rate must be a percentage in [0, 100], got {self.published_rate!r}"
            )

    @property
    def implied_resolved(self) -> int:
        """The resolved count the published rate implies, since one instance is 0.2 percent."""
        return round(self.published_rate * EXPECTED_INSTANCES / 100.0)

    @property
    def rate_is_exact(self) -> bool:
        exact = self.published_rate * EXPECTED_INSTANCES / 100.0
        return abs(exact - round(exact)) < 1e-9


@dataclass
class Artifact:
    """A fetched per-entry artifact, normalized to resolved instance IDs.

    `no_generation` and `no_logs` keep their **identities**, not just counts. PREREG section 3
    registers a pairwise-drop sensitivity analysis on `no_logs` instances, and a count cannot be
    dropped from a comparison. Discarding the ids would force T3.2 to re-fetch outside this
    derivation boundary, which is where reproducibility leaks.
    """

    folder: str
    split_dir: str
    artifact_format: str
    url: str
    sha256: str
    resolved: set[str]
    no_generation: set[str] = field(default_factory=set)
    no_logs: set[str] = field(default_factory=set)
    covered: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        """D2.3. An artifact that exists must be one that can be reasoned about."""
        for name in ("folder", "split_dir", "artifact_format", "url"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-blank string, got {value!r}")
        if len(self.sha256) != 64 or any(c not in "0123456789abcdef" for c in self.sha256):
            raise ValueError(f"sha256 must be 64 lowercase hex characters, got {self.sha256!r}")
        for name in ("resolved", "no_generation", "no_logs", "covered"):
            values = getattr(self, name)
            if any(not isinstance(item, str) for item in values):
                raise ValueError(f"{name} must contain only instance id strings")
        overlap = self.resolved & (self.no_generation | self.no_logs)
        if overlap:
            raise ValueError(
                f"{len(overlap)} id(s) are both resolved and unevaluated, "
                f"e.g. {sorted(overlap)[:3]}"
            )


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def fetch_bytes(url: str) -> bytes | None:
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


# --------------------------------------------------------------------------------------------
# Pure parsing and gates. No network, so the tests can exercise every branch.
# --------------------------------------------------------------------------------------------


def select_board(document: dict, name: str = BOARD_NAME) -> list:
    boards = document.get("leaderboards")
    if not isinstance(boards, list):
        raise GateFailure("gate 0: the board file has no 'leaderboards' array")
    board = next((b for b in boards if b.get("name") == name), None)
    if board is None:
        raise GateFailure(f"gate 0: no board named {name!r} in the pinned file")
    results = board.get("results")
    if not isinstance(results, list):
        raise GateFailure(f"gate 0: board {name!r} has no 'results' array")
    return results


def entries_in_published_order(results: list) -> list[Entry]:
    """Preserve array order. The pre-registration defines adjacency by it."""
    return [
        Entry(
            rank=index + 1,
            folder=row.get("folder") or "",
            published_rate=float(row["resolved"]),
            checked=row.get("checked"),
            date=row.get("date", ""),
        )
        for index, row in enumerate(results)
    ]


def parse_artifact_document(document: object, artifact_format: str, folder: str) -> dict:
    """Normalize either artifact layout, rejecting anything that is not exactly what it claims.

    Format B previously used truthiness, so a `"resolved": "false"` string counted as resolved.
    Only a real `bool` is accepted, and `isinstance(x, bool)` is checked rather than truthiness
    because every non-empty string, and every nonzero number, is truthy.
    """
    if not isinstance(document, dict):
        raise GateFailure(f"{folder}: artifact is not a JSON object")

    if artifact_format == FORMAT_RESOLVED_LIST:
        out = {}
        for key in ("resolved", "no_generation", "no_logs"):
            values = document.get(key, [])
            if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
                raise GateFailure(f"{folder}: {key!r} must be a list of instance ids")
            if len(set(values)) != len(values):
                repeated = sorted({v for v in values if values.count(v) > 1})
                raise GateFailure(
                    f"{folder}: {key!r} has duplicate ids, e.g. {repeated[:3]}; a set would "
                    "have hidden them and the count check would still have passed"
                )
            out[key] = set(values)
        overlap = out["resolved"] & (out["no_generation"] | out["no_logs"])
        if overlap:
            raise GateFailure(
                f"{folder}: {len(overlap)} id(s) are both resolved and unevaluated, "
                f"e.g. {sorted(overlap)[:3]}"
            )
        return {**out, "covered": set()}

    if artifact_format == FORMAT_INSTANCE_MAP:
        resolved: set[str] = set()
        for instance_id, record in document.items():
            if not isinstance(instance_id, str):
                raise GateFailure(f"{folder}: instance id {instance_id!r} is not a string")
            if not isinstance(record, dict):
                raise GateFailure(f"{folder}: record for {instance_id!r} is not an object")
            if "resolved" not in record:
                raise GateFailure(f"{folder}: record for {instance_id!r} has no 'resolved' field")
            flag = record["resolved"]
            if not isinstance(flag, bool):
                raise GateFailure(
                    f"{folder}: 'resolved' for {instance_id!r} is {flag!r}, which is "
                    f"{type(flag).__name__} and not a boolean; truthiness would have counted it"
                )
            if flag:
                resolved.add(instance_id)
        return {
            "resolved": resolved,
            "no_generation": set(),
            "no_logs": set(),
            "covered": set(document),
        }

    raise GateFailure(f"{folder}: unknown artifact format {artifact_format!r}")


def disqualify(entry: Entry, artifact: Artifact | None, canonical: set[str]) -> str | None:
    """Why this entry cannot be used, or None if it can. PREREG section 6."""
    if artifact is None:
        return "no artifact found under either split directory"
    if not entry.rate_is_exact:
        return (
            f"published rate {entry.published_rate} does not imply an exact count out of "
            f"{EXPECTED_INSTANCES}"
        )
    if len(artifact.resolved) != entry.implied_resolved:
        return (
            f"gate 3: derived resolved count {len(artifact.resolved)} does not match the "
            f"published {entry.implied_resolved}"
        )
    if not artifact.resolved <= canonical:
        stray = sorted(artifact.resolved - canonical)[:3]
        return f"gate 2: resolved ids outside the pinned instance set, e.g. {stray}"
    for name in ("no_generation", "no_logs"):
        ids = getattr(artifact, name)
        if not ids <= canonical:
            stray = sorted(ids - canonical)[:3]
            return (
                f"gate 2: {name} ids outside the pinned instance set, e.g. {stray}; the "
                "registered sensitivity analysis cannot drop an instance that is not in the set"
            )
    if artifact.covered and artifact.covered != canonical:
        return "gate 2: per-instance map does not cover the pinned instance set exactly"
    return None


def build_rows(chosen: list[Entry], artifacts: dict[str, Artifact], instance_ids: list[str]):
    """Long-format rows, per PLAN.md section 4. Sorted for byte-stability."""
    rows = [
        {
            "item_id": instance_id,
            "system": entry.folder,
            "run": 0,
            "instrument": INSTRUMENT,
            "label": 1 if instance_id in artifacts[entry.folder].resolved else 0,
        }
        for entry in chosen
        for instance_id in instance_ids
    ]
    rows.sort(key=lambda row: (row["item_id"], row["system"], row["run"], row["instrument"]))
    return rows


def run_gates(chosen: list[Entry], artifacts, rows, instance_ids: list[str]) -> None:
    """PREREG section 4, gates 1 to 4. Any failure stops the run."""
    canonical = set(instance_ids)
    by_system: dict[str, list] = {}
    for row in rows:
        by_system.setdefault(row["system"], []).append(row)

    for entry in chosen:
        labels = by_system.get(entry.folder, [])
        if len(labels) != EXPECTED_INSTANCES:
            raise GateFailure(
                f"gate 1: {entry.folder} has {len(labels)} labels, expected {EXPECTED_INSTANCES}"
            )
        if {row["item_id"] for row in labels} != canonical:
            raise GateFailure(f"gate 2: {entry.folder} does not cover the pinned instance set")
        resolved = sum(row["label"] for row in labels)
        if resolved != entry.implied_resolved:
            raise GateFailure(
                f"gate 3: {entry.folder} derived {resolved}, published implies "
                f"{entry.implied_resolved}"
            )

    keys = {(r["item_id"], r["system"], r["run"], r["instrument"]) for r in rows}
    if len(keys) != len(rows):
        raise GateFailure(f"gate 4: {len(rows) - len(keys)} duplicate rows on the uniqueness key")


def rows_to_csv(rows: list[dict]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(LABEL_COLUMNS), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def canonical_json(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def compare_manifest(expected: dict, observed: dict) -> list[str]:
    """Every digest the committed manifest declares must match what this run saw.

    Artifacts are compared **in order**. Adjacency is defined by the published order, so a run
    that selected the same twenty systems in a different sequence is a different experiment;
    comparing them as a mapping reported no problem when all twenty were reversed.

    Missing and extra derived entries are both errors, so a checksum cannot be dropped from the
    manifest to make a mismatch disappear.
    """
    problems = []
    for section in ("board", "dataset"):
        want = expected.get(section, {}).get("sha256")
        got = observed[section]["sha256"]
        if want != got:
            problems.append(f"{section}: expected {want}, observed {got}")

    want_list = [(a["system"], a["sha256"]) for a in expected.get("artifacts", [])]
    got_list = [(a["system"], a["sha256"]) for a in observed["artifacts"]]
    if [name for name, _ in want_list] != [name for name, _ in got_list]:
        if set(name for name, _ in want_list) == set(name for name, _ in got_list):
            problems.append(
                "artifacts: same systems in a different order; adjacency is defined by the "
                "published order, so the selection is not interchangeable"
            )
        else:
            differing = sorted(set(n for n, _ in want_list) ^ set(n for n, _ in got_list))[:3]
            problems.append(f"artifacts: selected systems differ, e.g. {differing}")
    else:
        for (name, want), (_, got) in zip(want_list, got_list, strict=True):
            if want != got:
                problems.append(f"artifact {name}: expected {want}, observed {got}")

    want_derived = {k: v for k, v in expected.get("derived", {}).items() if k != "rows"}
    got_derived = {k: v for k, v in observed["derived"].items() if k != "rows"}
    for name in sorted(set(want_derived) | set(got_derived)):
        if name not in want_derived:
            problems.append(f"derived {name}: present in this run but absent from the manifest")
        elif name not in got_derived:
            problems.append(f"derived {name}: declared in the manifest but not produced")
        elif want_derived[name] != got_derived[name]:
            problems.append(
                f"derived {name}: expected {want_derived[name]}, observed {got_derived[name]}"
            )
    return problems


# --------------------------------------------------------------------------------------------
# Network I/O
# --------------------------------------------------------------------------------------------


def gate_0_board() -> tuple[list, str]:
    payload = fetch_bytes(BOARD_URL)
    if payload is None:
        raise GateFailure(f"board not found at the pinned commit: {BOARD_URL}")
    digest = sha256(payload)
    if digest != BOARD_SHA256:
        raise GateFailure(
            "gate 0: the pinned board does not match its recorded digest.\n"
            f"  expected {BOARD_SHA256}\n  observed {digest}\n"
            "Upstream moved or the recorded digest is wrong. Do not proceed: the "
            "pre-registration defines adjacency by the array order in this exact file."
        )
    return select_board(json.loads(payload.decode("utf-8"))), digest


def fetch_artifact(folder: str) -> Artifact | None:
    """Try both artifact layouts, recording which one answered."""
    candidates = (
        ("verified", "results/results.json", FORMAT_RESOLVED_LIST),
        ("bash-only", "per_instance_details.json", FORMAT_INSTANCE_MAP),
    )
    for split_dir, suffix, artifact_format in candidates:
        url = f"{ARTIFACT_BASE}/{split_dir}/{folder}/{suffix}"
        payload = fetch_bytes(url)
        if payload is None:
            continue
        parsed = parse_artifact_document(
            json.loads(payload.decode("utf-8")), artifact_format, folder
        )
        return Artifact(
            folder=folder,
            split_dir=split_dir,
            artifact_format=artifact_format,
            url=url,
            sha256=sha256(payload),
            **parsed,
        )
    return None


def fetch_instance_ids() -> tuple[list[str], str]:
    """The canonical 500 instance IDs, from the pinned dataset revision.

    Downloads the complete parquet shard, which is the only granularity the store offers, then
    reads the `instance_id` column from it. No other column is used, and nothing is retained.
    """
    import pyarrow.parquet as pq  # experiments/ may use heavier dependencies than the engine

    payload = fetch_bytes(DATASET_URL)
    if payload is None:
        raise GateFailure(f"dataset not found at the pinned revision: {DATASET_URL}")
    table = pq.read_table(io.BytesIO(payload), columns=["instance_id"])
    return sorted(table.column("instance_id").to_pylist()), sha256(payload)


def select_lazily(entries: list[Entry], canonical: set[str]) -> tuple[list, dict, list]:
    """Walk the published order fetching only as far as the coverage rule needs.

    Replaces a fixed lookahead, which was an arbitrary bound on how far substitution could reach.
    """
    chosen: list[Entry] = []
    artifacts: dict[str, Artifact] = {}
    substitutions: list[dict] = []

    for entry in entries:
        if len(chosen) == N_TOP:
            break
        if not entry.folder:
            substitutions.append(
                {"rank": entry.rank, "folder": "", "reason": "board entry names no folder"}
            )
            continue
        artifact = fetch_artifact(entry.folder)
        reason = disqualify(entry, artifact, canonical)
        if reason is None:
            artifacts[entry.folder] = artifact
            chosen.append(entry)
        else:
            substitutions.append({"rank": entry.rank, "folder": entry.folder, "reason": reason})

    if len(chosen) < N_TOP:
        raise GateFailure(
            f"only {len(chosen)} of {N_TOP} entries cleared the coverage rule after exhausting "
            "the board; it does not support the registered family size"
        )
    return chosen, artifacts, substitutions


def clear_partials() -> None:
    """Remove leftover `.partial` files from an interrupted write.

    Deliberately **not** clearing the derived outputs. Doing that before the first network call
    meant any failure dirtied a clean clone with a deleted tracked aggregate. Existing outputs
    survive until every fetch, gate, and manifest check has passed, and are then replaced
    atomically. Staleness is caught downstream instead: T3.2 verifies every input checksum
    against the manifest before reading it.
    """
    if DERIVED.exists():
        for path in sorted(DERIVED.glob("*.partial")):
            path.unlink()


def atomic_write(path: Path, text: str) -> str:
    """Write via a temporary file and rename, so a partial write is never readable as complete."""
    temporary = path.with_name(path.name + ".partial")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)
    return sha256(text.encode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bootstrap",
        action="store_true",
        help="write the manifest instead of checking against it; required on first run",
    )
    parser.add_argument(
        "--fetch-date",
        help="canonical YYYY-MM-DD date recorded in the manifest; required with --bootstrap",
    )
    args = parser.parse_args(argv)

    if args.bootstrap and not args.fetch_date:
        parser.error("--bootstrap requires --fetch-date; a manifest must not invent its own date")

    if not args.bootstrap and not MANIFEST_PATH.exists():
        raise GateFailure(
            f"no committed manifest at {MANIFEST_PATH}. A normal run checks against it; use "
            "--bootstrap to create one, then review and commit it."
        )

    DERIVED.mkdir(exist_ok=True)
    MANIFESTS.mkdir(exist_ok=True)
    clear_partials()

    print("gate 0: verifying the published board before parsing it")
    results, board_digest = gate_0_board()
    entries = entries_in_published_order(results)
    print(f"  board verified, {len(entries)} entries in published order")

    instance_ids, dataset_digest = fetch_instance_ids()
    if len(instance_ids) != EXPECTED_INSTANCES:
        raise GateFailure(f"expected {EXPECTED_INSTANCES} instances, got {len(instance_ids)}")
    print(f"  instance set: {len(instance_ids)} ids at the pinned dataset revision")

    print("walking the published order, fetching only as far as the coverage rule needs")
    chosen, artifacts, substitutions = select_lazily(entries, set(instance_ids))
    print(f"  {len(chosen)} entries selected, {len(substitutions)} substitution(s)")
    for record in substitutions:
        print(f"    rank {record['rank']} {record['folder']}: {record['reason']}")

    rows = build_rows(chosen, artifacts, instance_ids)
    run_gates(chosen, artifacts, rows, instance_ids)
    print(f"  gates 1 to 4 passed on {len(rows)} rows")

    labels_csv = rows_to_csv(rows)
    unevaluated = canonical_json(
        {
            entry.folder: {
                "no_generation": sorted(artifacts[entry.folder].no_generation),
                "no_logs": sorted(artifacts[entry.folder].no_logs),
            }
            for entry in chosen
        }
    )
    aggregates = canonical_json(
        {
            "board": BOARD_NAME,
            "family_size": len(chosen),
            "n_items": EXPECTED_INSTANCES,
            "instrument": INSTRUMENT,
            "entries": [
                {
                    "rank": entry.rank,
                    "system": entry.folder,
                    "date": entry.date,
                    # `checked` is bool, null, or, for six board entries, a sentence. Null is
                    # absence; a string is the defect recon recorded, and a boolean test on it
                    # would read "false (...)" as true.
                    "checked": entry.checked if isinstance(entry.checked, bool) else None,
                    "checked_is_malformed": not isinstance(entry.checked, (bool, type(None))),
                    "checked_raw": (
                        str(entry.checked)
                        if not isinstance(entry.checked, (bool, type(None)))
                        else None
                    ),
                    "published_rate": entry.published_rate,
                    "resolved": entry.implied_resolved,
                    "artifact_format": artifacts[entry.folder].artifact_format,
                    "split_dir": artifacts[entry.folder].split_dir,
                    "no_generation": len(artifacts[entry.folder].no_generation),
                    "no_logs": len(artifacts[entry.folder].no_logs),
                }
                for entry in chosen
            ],
            "substitutions": substitutions,
        }
    )

    observed = {
        "board": {"url": BOARD_URL, "commit": BOARD_COMMIT, "sha256": board_digest},
        "dataset": {"url": DATASET_URL, "revision": DATASET_REVISION, "sha256": dataset_digest},
        "artifacts": [
            {
                "system": entry.folder,
                "url": artifacts[entry.folder].url,
                "sha256": artifacts[entry.folder].sha256,
            }
            for entry in chosen
        ],
        "derived": {
            "labels.csv": sha256(labels_csv.encode("utf-8")),
            "unevaluated.json": sha256(unevaluated.encode("utf-8")),
            "aggregates.json": sha256(aggregates.encode("utf-8")),
            "rows": len(rows),
        },
        "fetch_date": (
            args.fetch_date
            if args.bootstrap
            else json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["fetch_date"]
        ),
    }

    if args.bootstrap:
        atomic_write(MANIFEST_PATH, canonical_json(observed))
        print(f"  bootstrapped {MANIFEST_PATH.name}; review and commit it")
    else:
        problems = compare_manifest(json.loads(MANIFEST_PATH.read_text(encoding="utf-8")), observed)
        if problems:
            raise GateFailure(
                "the committed manifest does not match this run:\n  "
                + "\n  ".join(problems)
                + "\nUpstream moved, or the derivation changed. The manifest is an input; "
                "re-create it with --bootstrap only after deciding the change is intended."
            )
        print("  manifest matched: every upstream and derived digest as committed")

    atomic_write(DERIVED / "labels.csv", labels_csv)
    atomic_write(DERIVED / "unevaluated.json", unevaluated)
    atomic_write(DERIVED / "aggregates.json", aggregates)
    print(f"  wrote {len(rows)} rows plus the unevaluated sidecar, both untracked")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GateFailure as failure:
        print(f"\nSTOPPED: {failure}", file=sys.stderr)
        raise SystemExit(1) from failure
