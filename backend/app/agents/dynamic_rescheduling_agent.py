from typing import Any

from backend.app.optimization.optimizer import (
    OptimizationError,
    optimize_departures,
)


class DynamicReschedulingError(Exception):
    """Raised when dynamic rescheduling fails."""


def run_dynamic_rescheduling(
    baseline_trains: list[dict[str, Any]],
    track_sections: list[dict[str, Any]],
    validate_schedule,
    disruptions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Optimize, validate, and explain a proposed train schedule."""

    disruptions = disruptions or []

    # ---------------------------------------------------------
    # 1. Run the optimizer with any track disruptions
    # ---------------------------------------------------------

    try:
        result = optimize_departures(
            baseline_trains=baseline_trains,
            track_sections=track_sections,
            disruptions=disruptions,
        )

    except (
        OptimizationError,
        ValueError,
        KeyError,
        TypeError,
    ) as exc:
        raise DynamicReschedulingError(
            f"Dynamic rescheduling failed: {exc}"
        ) from exc

    optimized_trains = result.get("optimized_trains", [])

    # ---------------------------------------------------------
    # 2. Handle the case where no feasible schedule is found
    # ---------------------------------------------------------

    if not optimized_trains:
        return {
            "status": result.get("status", "UNKNOWN"),
            "message": result.get(
                "message",
                "No feasible departure-delay plan was found.",
            ),
            "optimized_trains": [],
            "total_added_departure_delay_minutes": None,
            "validation": {
                "passed": False,
                "integrity_errors": [
                    "The optimizer did not return a feasible schedule."
                ],
                "conflict_count": None,
                "conflicts": [],
            },
            "remaining_conflicts": [],
            "recommendations": [],
            "limitations": [
                "Uses fixed train routes and travel times.",
                "Uses a simplified track occupancy and headway model.",
                "Temporary track closures are modeled as fixed time windows.",
                "Does not replace railway signaling or safety validation.",
            ],
        }

    # ---------------------------------------------------------
    # 3. Validate the optimized schedule
    #    Pass the same disruptions to the validator.
    # ---------------------------------------------------------

    try:
        validation = validate_schedule(
            baseline_trains,
            optimized_trains,
            track_sections,
            disruptions=disruptions,
        )

    except (ValueError, KeyError, TypeError) as exc:
        raise DynamicReschedulingError(
            f"Schedule validation failed: {exc}"
        ) from exc

    # ---------------------------------------------------------
    # 4. Generate recommendations
    # ---------------------------------------------------------

    recommendations = []

    for train in optimized_trains:
        added_delay = train.get(
            "added_departure_delay_minutes",
            0,
        )

        if added_delay > 0:
            reason = (
                "The optimizer added departure delay to satisfy "
                "the configured track occupancy and headway constraints."
            )

            if disruptions:
                reason += (
                    " The schedule also accounts for the configured "
                    "temporary track closure windows."
                )

            recommendations.append({
                "train_id": train["train_id"],
                "added_departure_delay_minutes": added_delay,
                "reason": reason,
            })

    # ---------------------------------------------------------
    # 5. Return the rescheduling result
    # ---------------------------------------------------------

    return {
        "status": result["status"],
        "message": result.get(
            "message",
            "Rescheduling completed.",
        ),
        "baseline_train_count": len(baseline_trains),
        "optimized_train_count": len(optimized_trains),
        "optimized_trains": optimized_trains,
        "total_added_departure_delay_minutes": (
            result["total_added_departure_delay_minutes"]
        ),
        "validation": {
            "passed": validation["passed"],
            "integrity_errors": validation["integrity_errors"],
            "conflict_count": validation["conflict_count"],
            "conflicts": validation["conflicts"],
            "disruptions_checked": validation.get(
                "disruptions_checked",
                len(disruptions),
            ),
        },
        "remaining_conflicts": validation["conflicts"],
        "recommendations": recommendations,
        "limitations": [
            "Uses fixed train routes and travel times.",
            "Uses a simplified track occupancy and headway model.",
            "Temporary track closures are modeled as fixed time windows.",
            "Does not replace railway signaling or safety validation.",
        ],
    }