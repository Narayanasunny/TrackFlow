from backend.app.simulation.engine import detect_track_conflicts


def validate_optimized_schedule(
    baseline_trains,
    optimized_trains,
    track_sections,
    disruptions=None,
):
    """Check schedule integrity, track conflicts, and track closures."""

    errors = []
    disruptions = disruptions or []

    baseline_by_id = {
        train["train_id"]: train
        for train in baseline_trains
    }
    optimized_by_id = {
        train["train_id"]: train
        for train in optimized_trains
    }

    # Every baseline train must appear exactly once.
    if (
        len(optimized_by_id) != len(optimized_trains)
        or set(baseline_by_id) != set(optimized_by_id)
    ):
        errors.append(
            "Optimized train IDs do not match baseline train IDs."
        )

    # Check schedule integrity.
    for train_id in set(baseline_by_id) & set(optimized_by_id):
        original = baseline_by_id[train_id]
        updated = optimized_by_id[train_id]

        added_delay = updated.get(
            "added_departure_delay_minutes"
        )

        if (
            not isinstance(added_delay, int)
            or isinstance(added_delay, bool)
            or added_delay < 0
        ):
            errors.append(
                f"{train_id}: invalid added departure delay."
            )
            continue

        original_movements = original.get("movements", [])
        updated_movements = updated.get("movements", [])

        if len(original_movements) != len(updated_movements):
            errors.append(
                f"{train_id}: movement count changed."
            )
            continue

        for index, (before, after) in enumerate(
            zip(original_movements, updated_movements)
        ):
            for field in (
                "section_id",
                "from_station",
                "to_station",
            ):
                if before.get(field) != after.get(field):
                    errors.append(
                        f"{train_id}: movement {index} "
                        f"changed {field}."
                    )

            for field in ("departure", "arrival"):
                if (
                    after.get(field)
                    != before.get(field) + added_delay
                ):
                    errors.append(
                        f"{train_id}: movement {index} has an "
                        f"unexpected {field} time."
                    )

        if updated.get("scheduled_departure") != (
            original["scheduled_departure"] + added_delay
        ):
            errors.append(
                f"{train_id}: scheduled departure is inconsistent."
            )

        if updated.get("simulated_arrival") != (
            original["simulated_arrival"] + added_delay
        ):
            errors.append(
                f"{train_id}: simulated arrival is inconsistent."
            )

    # Recheck configured occupancy and headway constraints.
    conflicts = detect_track_conflicts(
        optimized_trains,
        track_sections,
    )

    if conflicts:
        errors.append(
            "Optimized schedule contains track occupancy or headway conflicts."
        )

    # Check temporary track closures.
    for disruption in disruptions:
        section_id = disruption.get("section_id")
        start = disruption.get("start_minute")
        end = disruption.get("end_minute")

        if (
            not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or start < 0
            or end <= start
        ):
            errors.append(
                f"Invalid disruption window for section {section_id}."
            )
            continue

        for train in optimized_trains:
            train_id = train.get("train_id")

            for movement in train.get("movements", []):
                if movement.get("section_id") != section_id:
                    continue

                departure = movement.get("departure")
                arrival = movement.get("arrival")

                if (
                    not isinstance(departure, int)
                    or isinstance(departure, bool)
                    or not isinstance(arrival, int)
                    or isinstance(arrival, bool)
                    or arrival <= departure
                ):
                    errors.append(
                        f"{train_id}: invalid movement times "
                        f"on disrupted section {section_id}."
                    )
                    continue

                # Half-open closure interval [start, end):
                # movements must not overlap it.
                if departure < end and arrival > start:
                    errors.append(
                        f"{train_id}: movement on {section_id} "
                        f"overlaps closure [{start}, {end})."
                    )

    return {
        "passed": not errors and not conflicts,
        "integrity_errors": errors,
        "conflict_count": len(conflicts),
        "conflicts": conflicts,
        "disruptions_checked": len(disruptions),
    }