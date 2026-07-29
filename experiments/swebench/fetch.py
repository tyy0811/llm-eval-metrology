#!/usr/bin/env python3
"""T3.1: fetch the pinned upstream artifacts and derive Experiment 1's label table.

**Nothing upstream is redistributed.** Under `docs/DECISIONS.md` D1.4 this repo ships a
deterministic fetch-and-derive pipeline plus checksums of what it must produce. The derived table
is written to `derived/` and left untracked; what is committed is this script, the digests of
every upstream file consumed, the expected checksums of the derived table, and de minimis
aggregates a reader can use to sanity-check the headline.

**Gate 0 comes before parsing.** The published board is fetched whole and its raw bytes are
verified against the sha256 recorded in `docs/recon_swebench.md`. The pre-registration defines
adjacency by the array order in that exact file, and the coverage rule needs the entries below
rank 20 if a substitution fires, so the file is the input rather than the recon note's summary of
it. Verifying before parsing turns "the board at that revision" from a trusted statement into a
checked one.

Gates 1 to 4 are the pre-registration's integrity gates and run before any table is written.

Network access is required, which is the trade D1.4 records: no offline reproduction, in exchange
for redistributing nothing and failing loudly when upstream moves.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
DERIVED = HERE / "derived"
MANIFESTS = HERE / "manifests"

# Pinned in docs/recon_swebench.md. Changing any of these is a plan-level act: it changes what
# "the board" and "the artifacts" mean, and every committed checksum below becomes stale.
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

    @property
    def implied_resolved(self) -> int:
        """The resolved count the published rate implies, since one instance is 0.2 percent."""
        exact = self.published_rate * EXPECTED_INSTANCES / 100.0
        return round(exact)

    @property
    def rate_is_exact(self) -> bool:
        exact = self.published_rate * EXPECTED_INSTANCES / 100.0
        return abs(exact - round(exact)) < 1e-9


@dataclass
class Artifact:
    """A fetched per-entry artifact, normalized to resolved instance IDs."""

    folder: str
    split_dir: str
    artifact_format: str
    url: str
    sha256: str
    resolved: set[str]
    no_generation: int = 0
    no_logs: int = 0
    covered: set[str] = field(default_factory=set)


def fetch_bytes(url: str) -> bytes | None:
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def gate_0_board() -> tuple[list, str]:
    """Fetch the published board whole and verify its bytes before parsing them."""
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

    boards = json.loads(payload.decode("utf-8"))["leaderboards"]
    board = next((b for b in boards if b["name"] == BOARD_NAME), None)
    if board is None:
        raise GateFailure(f"gate 0: no board named {BOARD_NAME!r} in the pinned file")
    return board["results"], digest


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


def fetch_artifact(folder: str) -> Artifact | None:
    """Try both artifact layouts, recording which one answered.

    `evaluation/verified/` enumerates only resolved IDs; `evaluation/bash-only/` maps every
    instance to a boolean. Recon found 47 of 180 board entries live under the second, so a
    fetcher written against one layout silently drops a quarter of the board.
    """
    candidates = (
        ("verified", "results/results.json", "resolved-id-list"),
        ("bash-only", "per_instance_details.json", "per-instance-map"),
    )
    for split_dir, suffix, artifact_format in candidates:
        url = f"{ARTIFACT_BASE}/{split_dir}/{folder}/{suffix}"
        payload = fetch_bytes(url)
        if payload is None:
            continue
        document = json.loads(payload.decode("utf-8"))
        if artifact_format == "resolved-id-list":
            resolved = set(document.get("resolved", []))
            no_generation = len(document.get("no_generation", []))
            no_logs = len(document.get("no_logs", []))
            covered: set[str] = set()
        else:
            resolved = {key for key, value in document.items() if value.get("resolved")}
            no_generation = 0
            no_logs = 0
            covered = set(document)
        return Artifact(
            folder=folder,
            split_dir=split_dir,
            artifact_format=artifact_format,
            url=url,
            sha256=sha256(payload),
            resolved=resolved,
            no_generation=no_generation,
            no_logs=no_logs,
            covered=covered,
        )
    return None


def fetch_instance_ids() -> tuple[list[str], str]:
    """The canonical 500 instance IDs, from the pinned dataset revision."""
    import pyarrow.parquet as pq  # experiments/ may use heavier dependencies than the engine

    payload = fetch_bytes(DATASET_URL)
    if payload is None:
        raise GateFailure(f"dataset not found at the pinned revision: {DATASET_URL}")
    table = pq.read_table(io.BytesIO(payload), columns=["instance_id"])
    return sorted(table.column("instance_id").to_pylist()), sha256(payload)


def select_with_coverage_rule(
    entries: list[Entry],
    artifacts: dict[str, Artifact],
    instance_ids: list[str],
) -> tuple[list[Entry], list[dict]]:
    """Walk the published order, substituting downward when an entry fails a gate.

    PREREG section 6: an entry lacking complete artifacts, or failing an integrity gate, is
    replaced by the next entry down, and every substitution is recorded.
    """
    canonical = set(instance_ids)
    chosen: list[Entry] = []
    substitutions: list[dict] = []

    for entry in entries:
        if len(chosen) == N_TOP:
            break
        reason = None
        artifact = artifacts.get(entry.folder)
        if artifact is None:
            reason = "no artifact found under either split directory"
        elif not entry.rate_is_exact:
            reason = (
                f"published rate {entry.published_rate} does not imply an exact count out of "
                f"{EXPECTED_INSTANCES}"
            )
        elif len(artifact.resolved) != entry.implied_resolved:
            reason = (
                f"gate 3: derived resolved count {len(artifact.resolved)} does not match the "
                f"published {entry.implied_resolved}"
            )
        elif not artifact.resolved <= canonical:
            stray = sorted(artifact.resolved - canonical)[:3]
            reason = f"gate 2: resolved ids outside the pinned instance set, e.g. {stray}"
        elif artifact.covered and set(artifact.covered) != canonical:
            reason = "gate 2: per-instance map does not cover the pinned instance set exactly"

        if reason is None:
            chosen.append(entry)
        else:
            substitutions.append({"rank": entry.rank, "folder": entry.folder, "reason": reason})

    if len(chosen) < N_TOP:
        raise GateFailure(
            f"only {len(chosen)} of {N_TOP} entries cleared the coverage rule; the board does "
            "not support the registered family size"
        )
    return chosen, substitutions


def build_rows(chosen: list[Entry], artifacts: dict[str, Artifact], instance_ids: list[str]):
    """Long-format rows, per PLAN.md section 4. Sorted for byte-stability."""
    rows = []
    for entry in chosen:
        resolved = artifacts[entry.folder].resolved
        for instance_id in instance_ids:
            rows.append(
                {
                    "item_id": instance_id,
                    "system": entry.folder,
                    "run": 0,
                    "instrument": INSTRUMENT,
                    "label": 1 if instance_id in resolved else 0,
                }
            )
    rows.sort(key=lambda row: (row["item_id"], row["system"], row["run"], row["instrument"]))
    return rows


def run_gates(chosen: list[Entry], artifacts, rows, instance_ids: list[str]) -> None:
    """PREREG section 4, gates 1 to 4. Any failure stops the run."""
    canonical = set(instance_ids)

    for entry in chosen:
        labels = [row for row in rows if row["system"] == entry.folder]
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)

    DERIVED.mkdir(exist_ok=True)
    MANIFESTS.mkdir(exist_ok=True)

    print("gate 0: verifying the published board before parsing it")
    results, board_digest = gate_0_board()
    entries = entries_in_published_order(results)
    print(f"  board verified, {len(entries)} entries in published order")

    instance_ids, dataset_digest = fetch_instance_ids()
    if len(instance_ids) != EXPECTED_INSTANCES:
        raise GateFailure(f"expected {EXPECTED_INSTANCES} instances, got {len(instance_ids)}")
    print(f"  instance set: {len(instance_ids)} ids at the pinned dataset revision")

    print("fetching per-entry artifacts, walking the published order")
    artifacts: dict[str, Artifact] = {}
    for entry in entries:
        if len(artifacts) >= N_TOP + 10:  # enough headroom for the coverage rule
            break
        if not entry.folder:
            continue
        artifact = fetch_artifact(entry.folder)
        if artifact is not None:
            artifacts[entry.folder] = artifact

    chosen, substitutions = select_with_coverage_rule(entries, artifacts, instance_ids)
    print(f"  {len(chosen)} entries selected, {len(substitutions)} substitution(s)")
    for record in substitutions:
        print(f"    rank {record['rank']} {record['folder']}: {record['reason']}")

    rows = build_rows(chosen, artifacts, instance_ids)
    run_gates(chosen, artifacts, rows, instance_ids)
    print(f"  gates 1 to 4 passed on {len(rows)} rows")

    table_path = DERIVED / "labels.csv"
    with open(table_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["item_id", "system", "run", "instrument", "label"]
        )
        writer.writeheader()
        writer.writerows(rows)
    table_digest = sha256(table_path.read_bytes())

    aggregates = {
        "board": BOARD_NAME,
        "family_size": len(chosen),
        "n_items": EXPECTED_INSTANCES,
        "instrument": INSTRUMENT,
        "entries": [
            {
                "rank": entry.rank,
                "system": entry.folder,
                "published_rate": entry.published_rate,
                "resolved": entry.implied_resolved,
                "artifact_format": artifacts[entry.folder].artifact_format,
                "split_dir": artifacts[entry.folder].split_dir,
                "no_generation": artifacts[entry.folder].no_generation,
                "no_logs": artifacts[entry.folder].no_logs,
            }
            for entry in chosen
        ],
        "substitutions": substitutions,
    }
    (DERIVED / "aggregates.json").write_text(
        json.dumps(aggregates, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    manifest = {
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
        "derived": {"labels.csv": table_digest, "rows": len(rows)},
    }
    (MANIFESTS / "upstream_digests.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(f"  derived table: {len(rows)} rows, sha256 {table_digest[:16]}, untracked")
    print(f"  manifests written to {MANIFESTS.relative_to(HERE.parent.parent)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GateFailure as failure:
        print(f"\nSTOPPED: {failure}", file=sys.stderr)
        raise SystemExit(1) from failure
