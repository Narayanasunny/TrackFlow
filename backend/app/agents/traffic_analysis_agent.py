
from collections import Counter, defaultdict

from backend.app.simulation.engine import (
    load_dataset,
    run_baseline_simulation,
)


def analyze_traffic():
    """
    Analyze the current synthetic railway traffic.

    Uses existing simulation results; it does not modify train schedules
    or issue real railway movement instructions.
    """

    dataset = load_dataset()
    baseline = run_baseline_simulation()

    trains = baseline.get("trains", [])
    conflicts = baseline.get("conflicts", [])

    train_conflict_counts = Counter()
    section_conflict_counts = Counter()
    conflict_type_counts = Counter()
    conflict_details = []

    for conflict in conflicts:
        train_ids = set()

        # Support the common train ID fields used by conflict records.
        for key in ("train_id", "train_a", "train_b", "train_1", "train_2"):
            value = conflict.get(key)
            if isinstance(value, str):
                train_ids.add(value)

        # Some conflict records store train IDs in a list.
        involved = conflict.get("train_ids", [])
        if isinstance(involved, list):
            train_ids.update(
                train_id
                for train_id in involved
                if isinstance(train_id, str)
            )

        for train_id in train_ids:
            train_conflict_counts[train_id] += 1

        section_id = conflict.get("section_id", "unknown")
        section_conflict_counts[section_id] += 1

        conflict_type = conflict.get(
            "conflict_type",
            conflict.get("type", "unspecified"),
        )
        conflict_type_counts[conflict_type] += 1

        conflict_details.append(conflict)

    most_affected_trains = [
        {
            "train_id": train_id,
            "conflict_count": count,
        }
        for train_id, count in train_conflict_counts.most_common()
    ]

    most_affected_sections = [
        {
            "section_id": section_id,
            "conflict_count": count,
        }
        for section_id, count in section_conflict_counts.most_common()
    ]

    conflict_types = [
        {
            "type": conflict_type,
            "count": count,
        }
        for conflict_type, count in conflict_type_counts.most_common()
    ]

    recommendations = []

    if conflicts:
        recommendations.append(
            "Review the model-detected conflicts before evaluating a revised schedule."
        )
    else:
        recommendations.append(
            "No conflicts were detected by the current configured model checks."
        )

    if most_affected_sections:
        busiest_conflict_section = most_affected_sections[0]["section_id"]
        recommendations.append(
            f"Inspect {busiest_conflict_section}, which has the highest "
            "count of detected conflicts in this simulation."
        )

    return {
        "agent": "traffic_analysis",
        "analysis_type": "synthetic_traffic_analysis",
        "network_summary": {
            "station_count": len(dataset.get("stations", [])),
            "track_section_count": len(dataset.get("track_sections", [])),
            "train_count": len(trains),
            "baseline_conflict_count": len(conflicts),
            "total_delay_minutes": baseline.get("total_delay_minutes", 0),
        },
        "conflict_types": conflict_types,
        "most_affected_trains": most_affected_trains,
        "most_affected_sections": most_affected_sections,
        "recommendations": recommendations,
        "conflicts": conflict_details,
        "limitations": [
            "Uses synthetic project data.",
            "Counts reflect the existing conflict detector's output.",
            "This analysis is not a real railway safety assessment.",
        ],
    }
