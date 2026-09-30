"""Does Trackrecord find the planted problems without being told?

For each seed we generate a fresh fictitious world, score it, and compare with
the ground truth: which documents were planted as dangerous, unclear or broken,
and which knowledge gap exists. We also report false alarms, how quickly
problems are detected, and what happens without the safeguards (ablations).

    python -m trackrecord.evaluate --seeds 20
"""
import argparse
import json
import statistics
import tempfile
from datetime import date, timedelta
from pathlib import Path

from . import db as store
from . import generate, scoring

FLAGGED = {"dangerous", "broken", "unclear"}
CHANGE_DATE = date(2026, 7, 1)   # the planted rule change behind TR-MC-01


def _detected(result, doc_id):
    return result["versions"][f"{doc_id}@v1"]["quadrant"]


def _gap_found(gaps):
    found = any(gap["is_gap"] and "flexi" in gap["stems"] for gap in gaps)
    false = sum(1 for gap in gaps if gap["is_gap"] and "flexi" not in gap["stems"])
    return found, false


def _first_detection(db, doc_id, expected, days, **flags):
    for as_of in days:
        result = scoring.compute(db, as_of, **flags)
        version = result["versions"][f"{doc_id}@v1"]
        if version["quadrant"] == expected:
            return as_of, version["uses"]
    return None, None


def evaluate_seed(seed, directory):
    path = Path(directory) / f"eval-{seed}.sqlite3"
    generate.build(path, seed=seed)
    today = generate.TODAY
    with store.connect(path) as db:
        truth = {row["document_id"]: row["expected"] for row in db.execute("SELECT * FROM ground_truth")}
        planted = {doc: label for doc, label in truth.items() if label != "gap"}
        full = scoring.compute(db, today)
        raw = scoring.compute(db, today, smooth=False, min_evidence=False)
        no_recency = scoring.compute(db, today, recency=False)
        normal = [v["document_id"] for v in full["versions"].values() if v["document_id"] not in planted]

        def score(result):
            return {
                "exact": {doc: _detected(result, doc) == label for doc, label in planted.items()},
                "false_alarms": [doc for doc in normal if _detected(result, doc) in FLAGGED],
            }

        segment = full["versions"]["TR-VAK-01@v1"]["segment"]
        gap_found, false_gaps = _gap_found(scoring.gaps(db, today))
        weekly = [CHANGE_DATE + timedelta(days=7 * week) for week in range(0, 14)]
        weekly = [day for day in weekly if day <= today]
        change_hit, _ = _first_detection(db, "TR-MC-01", "dangerous", weekly)
        change_hit_no_recency, _ = _first_detection(db, "TR-MC-01", "dangerous", weekly, recency=False)
        monthly = [generate.START + timedelta(days=30 * month) for month in range(1, 13)]
        _, uses_to_detect = _first_detection(db, "TR-VAK-01", "dangerous", monthly)
    path.unlink(missing_ok=True)
    return {
        "seed": seed,
        "full": score(full), "raw": score(raw), "no_recency": score(no_recency),
        "segment_correct": bool(segment and (segment["dimension"], segment["value"]) == ("statute", "arbeider")),
        "gap_found": gap_found, "false_gaps": false_gaps,
        "days_to_detect_change": (change_hit - CHANGE_DATE).days if change_hit else None,
        "days_to_detect_change_no_recency": (change_hit_no_recency - CHANGE_DATE).days if change_hit_no_recency else None,
        "uses_to_detect_vak01": uses_to_detect,
        "normal_documents": len(normal),
    }


def summarize(runs):
    seeds = len(runs)
    planted = list(runs[0]["full"]["exact"])

    def found(variant):
        return sum(sum(run[variant]["exact"].values()) for run in runs)

    def alarms(variant):
        return sum(len(run[variant]["false_alarms"]) for run in runs)

    def median(values):
        values = [value for value in values if value is not None]
        return statistics.median(values) if values else None

    normal_total = sum(run["normal_documents"] for run in runs)
    return {
        "seeds": seeds,
        "planted_total": seeds * len(planted),
        "per_document": {doc: sum(run["full"]["exact"][doc] for run in runs) for doc in planted},
        "found": found("full"), "false_alarms": alarms("full"), "normal_total": normal_total,
        "segment_correct": sum(run["segment_correct"] for run in runs),
        "gap_found": sum(run["gap_found"] for run in runs), "false_gaps": sum(run["false_gaps"] for run in runs),
        "median_days_to_detect_change": median(run["days_to_detect_change"] for run in runs),
        "missed_change": sum(run["days_to_detect_change"] is None for run in runs),
        "median_days_to_detect_change_no_recency": median(run["days_to_detect_change_no_recency"] for run in runs),
        "missed_change_no_recency": sum(run["days_to_detect_change_no_recency"] is None for run in runs),
        "median_uses_to_detect_vak01": median(run["uses_to_detect_vak01"] for run in runs),
        "ablations": {
            "zonder_afvlakking_en_minimum_bewijs": {"found": found("raw"), "false_alarms": alarms("raw")},
            "zonder_recentheid": {"found": found("no_recency"), "false_alarms": alarms("no_recency")},
        },
    }


def report(summary):
    s = {"first_seed": 1, **summary}
    lines = [
        f"Evaluatie over {s['seeds']} niet eerder geziene synthetische werelden "
        f"(seeds {s['first_seed']}-{s['first_seed'] + s['seeds'] - 1})",
        f"  Geplante documentproblemen juist geclassificeerd: {s['found']}/{s['planted_total']}",
    ]
    lines += [f"    {doc}: {hits}/{s['seeds']}" for doc, hits in s["per_document"].items()]
    lines += [
        f"  Valse alarmen bij normale documenten: {s['false_alarms']}/{s['normal_total']}",
        f"  Juiste context gevonden (arbeiders bij TR-VAK-01): {s['segment_correct']}/{s['seeds']}",
        f"  Kennislacune (flexi-jobs) gevonden: {s['gap_found']}/{s['seeds']} · valse lacunes: {s['false_gaps']}",
        f"  Regelwijziging 1 juli (TR-MC-01) gedetecteerd na mediaan {s['median_days_to_detect_change']} dagen"
        f" (gemist in {s['missed_change']} werelden)",
        f"    zonder recentheid: mediaan {s['median_days_to_detect_change_no_recency']} dagen"
        f" (gemist in {s['missed_change_no_recency']} werelden)",
        f"  TR-VAK-01 gedetecteerd na mediaan {s['median_uses_to_detect_vak01']} gebruiken",
        "  Ablaties:",
    ]
    for name, values in s["ablations"].items():
        lines.append(f"    {name.replace('_', ' ')}: {values['found']}/{s['planted_total']} gevonden, "
                     f"{values['false_alarms']}/{s['normal_total']} valse alarmen")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seeds", type=int, default=20)
    # Seeds 1-10 were used while designing the rules; report on unseen worlds.
    parser.add_argument("--first-seed", type=int, default=101)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        runs = [evaluate_seed(seed, directory) for seed in range(args.first_seed, args.first_seed + args.seeds)]
    summary = summarize(runs)
    summary["first_seed"] = args.first_seed
    store.DATA_DIR.mkdir(parents=True, exist_ok=True)
    (store.DATA_DIR / "evaluation.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(report(summary))


if __name__ == "__main__":
    main()
