from typing import Any


def explain_optimization(
    baseline_trains: list[dict[str, Any]],
    optimized_trains: list[dict[str, Any]],
    baseline_conflicts: list[dict[str, Any]] | None = None,
    remaining_conflicts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Explain the differences between baseline and optimized schedules.

    Uses actual schedule values and conflict records.
    Does not modify train schedules or issue railway movement instructions.
    """

    baseline_conflicts = baseline_conflicts or []
    remaining_conflicts = remaining_conflicts or []

    baseline_by_id = {
        train["train_id"]: train
        for train in baseline_trains
    }

    optimized_by_id = {
        train["train_id"]: train
        for train in optimized_trains
    }

    train_comparisons = []
    explanations = []

    for train_id, optimized_train in optimized_by_id.items():
        baseline_train = baseline_by_id.get(train_id)

        if baseline_train is None:
            continue

        original_departure = baseline_train.get("scheduled_departure", 0)
        optimized_departure = optimized_train.get("scheduled_departure", 0)

        original_arrival = baseline_train.get("simulated_arrival", 0)
        optimized_arrival = optimized_train.get("simulated_arrival", 0)

        added_departure_delay = optimized_train.get(
            "added_departure_delay_minutes",
            optimized_departure - original_departure,
        )

        arrival_change = optimized_arrival - original_arrival

        comparison = {
            "train_id": train_id,
            "train_name": optimized_train.get("train_name", train_id),
            "original_departure": original_departure,
            "optimized_departure": optimized_departure,
            "added_departure_delay_minutes": added_departure_delay,
            "original_arrival": original_arrival,
            "optimized_arrival": optimized_arrival,
            "arrival_change_minutes": arrival_change,
            "original_delay_minutes": baseline_train.get("delay_minutes", 0),
            "optimized_delay_minutes": optimized_train.get("delay_minutes", 0),
        }

        train_comparisons.append(comparison)

        if added_departure_delay > 0:
            explanations.append({
                "train_id": train_id,
                "summary": (
                    f"{train_id} was assigned {added_departure_delay} "
                    "additional departure-delay minutes by the optimizer."
                ),
                "departure_change_minutes": added_departure_delay,
                "arrival_change_minutes": arrival_change,
                "reason": (
                    "The optimizer selected this delay while satisfying "
                    "its configured track occupancy and headway constraints. "
                    "The exact cause requires examining the train's "
                    "conflict records and optimization constraints."
                ),
            })

    train_comparisons.sort(
        key=lambda item: item["added_departure_delay_minutes"],
        reverse=True,
    )

    explanations.sort(
        key=lambda item: item["departure_change_minutes"],
        reverse=True,
    )

    return {
        "agent": "explainability",
        "analysis_type": "schedule_comparison",
        "summary": {
            "baseline_train_count": len(baseline_trains),
            "optimized_train_count": len(optimized_trains),
            "trains_with_added_departure_delay": len(explanations),
            "baseline_conflict_count": len(baseline_conflicts),
            "remaining_conflict_count": len(remaining_conflicts),
        },
        "train_comparisons": train_comparisons,
        "explanations": explanations,
        "conflict_context": {
            "baseline_conflicts": baseline_conflicts,
            "remaining_conflicts": remaining_conflicts,
        },
        "limitations": [
            "Explanations are based on schedule differences and supplied conflict records.",
            "A departure delay alone does not establish the exact cause of an optimization decision.",
            "The optimizer uses a simplified synthetic railway model.",
            "This agent does not provide real railway safety assessments.",
        ],
    }


def analyze_what_if(
    baseline_trains: list[dict[str, Any]],
    disrupted_trains: list[dict[str, Any]],
    optimized_trains: list[dict[str, Any]],
    baseline_conflicts: list[dict[str, Any]] | None = None,
    disrupted_conflicts: list[dict[str, Any]] | None = None,
    optimized_conflicts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Compare baseline, disrupted, and optimized simulation results.

    This function analyzes supplied results; it does not run a disruption
    or modify any schedules.
    """

    baseline_conflicts = baseline_conflicts or []
    disrupted_conflicts = disrupted_conflicts or []
    optimized_conflicts = optimized_conflicts or []

    baseline_by_id = {
        train["train_id"]: train
        for train in baseline_trains
    }

    disrupted_by_id = {
        train["train_id"]: train
        for train in disrupted_trains
    }

    optimized_by_id = {
        train["train_id"]: train
        for train in optimized_trains
    }

    comparisons = []

    for train_id, baseline_train in baseline_by_id.items():
        disrupted_train = disrupted_by_id.get(train_id)
        optimized_train = optimized_by_id.get(train_id)

        if disrupted_train is None or optimized_train is None:
            continue

        comparisons.append({
            "train_id": train_id,
            "baseline_departure": baseline_train.get("scheduled_departure", 0),
            "disrupted_departure": disrupted_train.get("scheduled_departure", 0),
            "optimized_departure": optimized_train.get("scheduled_departure", 0),
            "baseline_arrival": baseline_train.get("simulated_arrival", 0),
            "disrupted_arrival": disrupted_train.get("simulated_arrival", 0),
            "optimized_arrival": optimized_train.get("simulated_arrival", 0),
            "added_departure_delay_minutes": optimized_train.get(
                "added_departure_delay_minutes",
                0,
            ),
        })

    return {
        "agent": "explainability",
        "analysis_type": "what_if_comparison",
        "conflict_summary": {
            "baseline_conflicts": len(baseline_conflicts),
            "disrupted_conflicts": len(disrupted_conflicts),
            "optimized_conflicts": len(optimized_conflicts),
        },
        "train_comparisons": comparisons,
        "limitations": [
            "Compares results supplied by the caller.",
            "Does not generate a disruption or run optimization itself.",
            "Results apply only to the project's configured synthetic model.",
        ],
    }