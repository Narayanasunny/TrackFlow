from typing import Any

from ortools.sat.python import cp_model


class OptimizationError(Exception):
    """Raised when the optimizer receives invalid input or fails."""


def _is_valid_integer(value: Any) -> bool:
    """Return True for integers, but not booleans."""
    return isinstance(value, int) and not isinstance(value, bool)


def _is_double_track(section: dict[str, Any]) -> bool:
    """
    Determine whether a section is double-track.

    Supports common representations in track_sections.json:
    - is_double_track: true
    - track_type: "double"
    - track_type: "double_track"
    - tracks: 2
    """
    if section.get("is_double_track") is True:
        return True

    track_type = str(section.get("track_type", "")).lower()

    if track_type in ("double", "double_track", "double track"):
        return True

    return section.get("tracks") == 2


def _validate_disruptions(
    disruptions: list[dict[str, Any]],
    section_ids: set[str],
) -> None:
    """Validate temporary track closure definitions."""

    for index, disruption in enumerate(disruptions):
        if not isinstance(disruption, dict):
            raise OptimizationError(
                f"Disruption at index {index} must be a dictionary."
            )

        section_id = disruption.get("section_id")
        start = disruption.get("start_minute")
        end = disruption.get("end_minute")

        if section_id not in section_ids:
            raise OptimizationError(
                f"Disruption references unknown section: {section_id}"
            )

        if (
            not _is_valid_integer(start)
            or not _is_valid_integer(end)
            or start < 0
            or end <= start
        ):
            raise OptimizationError(
                f"Invalid disruption window for section {section_id}. "
                "Expected non-negative integer start_minute and "
                "end_minute, with end_minute > start_minute."
            )


def optimize_departures(
    baseline_trains: list[dict[str, Any]],
    track_sections: list[dict[str, Any]],
    max_departure_delay: int = 60,
    time_limit_seconds: float = 10.0,
    disruptions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Minimize total added train departure delay.

    The model:
    - Preserves train routes and movement durations.
    - Enforces track occupancy and headway constraints.
    - Supports temporary track closures.
    - Minimizes the sum of added departure delays.

    A disruption is represented as:
    {
        "section_id": "SEC_DE",
        "start_minute": 30,
        "end_minute": 50
    }

    The closure interval is half-open: [start_minute, end_minute).
    A movement must finish at or before the closure start, or begin
    at or after the closure end.

    This is a preliminary scheduling model, not a complete railway
    signaling or safety-certified system.
    """

    disruptions = disruptions or []

    # ---------------------------------------------------------
    # 1. Validate optimizer parameters
    # ---------------------------------------------------------

    if (
        not _is_valid_integer(max_departure_delay)
        or max_departure_delay < 0
    ):
        raise OptimizationError(
            "max_departure_delay must be a non-negative integer."
        )

    if (
        not isinstance(time_limit_seconds, (int, float))
        or isinstance(time_limit_seconds, bool)
        or time_limit_seconds <= 0
    ):
        raise OptimizationError(
            "time_limit_seconds must be greater than zero."
        )

    if not isinstance(baseline_trains, list):
        raise OptimizationError("baseline_trains must be a list.")

    if not isinstance(track_sections, list):
        raise OptimizationError("track_sections must be a list.")

    # ---------------------------------------------------------
    # 2. Validate track sections
    # ---------------------------------------------------------

    sections_by_id = {}

    for section in track_sections:
        section_id = section.get("section_id")

        if not section_id:
            raise OptimizationError(
                "Every track section must have a section_id."
            )

        if section_id in sections_by_id:
            raise OptimizationError(
                f"Duplicate track section ID: {section_id}"
            )

        headway = section.get("minimum_headway_minutes", 0)

        if (
            not _is_valid_integer(headway)
            or headway < 0
        ):
            raise OptimizationError(
                f"Invalid minimum_headway_minutes for {section_id}."
            )

        sections_by_id[section_id] = section

    section_ids = set(sections_by_id)

    # ---------------------------------------------------------
    # 3. Validate trains and movements
    # ---------------------------------------------------------

    train_ids = set()

    for train in baseline_trains:
        train_id = train.get("train_id")

        if not train_id:
            raise OptimizationError(
                "Every train must have a train_id."
            )

        if train_id in train_ids:
            raise OptimizationError(
                f"Duplicate train ID: {train_id}"
            )

        train_ids.add(train_id)

        if not _is_valid_integer(train.get("scheduled_departure")):
            raise OptimizationError(
                f"{train_id}: scheduled_departure must be an integer."
            )

        if not _is_valid_integer(train.get("simulated_arrival")):
            raise OptimizationError(
                f"{train_id}: simulated_arrival must be an integer."
            )

        movements = train.get("movements")

        if not isinstance(movements, list):
            raise OptimizationError(
                f"{train_id}: movements must be a list."
            )

        for movement in movements:
            section_id = movement.get("section_id")

            if section_id not in section_ids:
                raise OptimizationError(
                    f"{train_id}: unknown track section {section_id}."
                )

            departure = movement.get("departure")
            arrival = movement.get("arrival")

            if (
                not _is_valid_integer(departure)
                or not _is_valid_integer(arrival)
                or departure < 0
                or arrival <= departure
            ):
                raise OptimizationError(
                    f"{train_id}: invalid movement times "
                    f"on section {section_id}."
                )

    # ---------------------------------------------------------
    # 4. Validate disruptions
    # ---------------------------------------------------------

    _validate_disruptions(
        disruptions=disruptions,
        section_ids=section_ids,
    )

    # ---------------------------------------------------------
    # 5. Create CP-SAT model
    # ---------------------------------------------------------

    model = cp_model.CpModel()

    # One departure delay variable per train.
    delay_vars = {}

    for train in baseline_trains:
        train_id = train["train_id"]

        delay_vars[train_id] = model.NewIntVar(
            0,
            max_departure_delay,
            f"delay_{train_id}",
        )

    # ---------------------------------------------------------
    # 6. Enforce track occupancy and headway constraints
    # ---------------------------------------------------------

    movements_by_section = {
        section_id: []
        for section_id in section_ids
    }

    for train in baseline_trains:
        train_id = train["train_id"]

        for movement_index, movement in enumerate(
            train.get("movements", [])
        ):
            section_id = movement["section_id"]

            movements_by_section[section_id].append(
                {
                    "train_id": train_id,
                    "movement_index": movement_index,
                    "departure": movement["departure"],
                    "arrival": movement["arrival"],
                    "from_station": movement.get("from_station"),
                    "to_station": movement.get("to_station"),
                }
            )

    for section_id, movements in movements_by_section.items():
        section = sections_by_id[section_id]

        headway = section.get(
            "minimum_headway_minutes",
            0,
        )

        double_track = _is_double_track(section)

        for i in range(len(movements)):
            for j in range(i + 1, len(movements)):
                first = movements[i]
                second = movements[j]

                # A train cannot be paired with itself.
                if first["train_id"] == second["train_id"]:
                    continue

                first_delay = delay_vars[first["train_id"]]
                second_delay = delay_vars[second["train_id"]]

                first_start = first["departure"]
                first_end = first["arrival"]

                second_start = second["departure"]
                second_end = second["arrival"]

                first_direction = (
                    first["from_station"],
                    first["to_station"],
                )

                second_direction = (
                    second["from_station"],
                    second["to_station"],
                )

                same_direction = (
                    first_direction == second_direction
                )

                # On double-track sections, opposite-direction
                # trains are assumed to use separate tracks.
                if double_track and not same_direction:
                    continue

                # Same direction: apply configured headway.
                # Single-track opposite direction: no extra gap
                # beyond non-overlapping occupancy in this model.
                required_gap = headway if same_direction else 0

                # Boolean determines which train goes first.
                first_before_second = model.NewBoolVar(
                    f"{section_id}_{i}_before_{j}"
                )

                # If first_before_second is true:
                # first movement finishes before second begins.
                model.Add(
                    first_end + first_delay + required_gap
                    <= second_start + second_delay
                ).OnlyEnforceIf(first_before_second)

                # Otherwise, second movement finishes before first.
                model.Add(
                    second_end + second_delay + required_gap
                    <= first_start + first_delay
                ).OnlyEnforceIf(
                    first_before_second.Not()
                )

    # ---------------------------------------------------------
    # 7. Enforce temporary track closures
    # ---------------------------------------------------------

    for disruption_index, disruption in enumerate(disruptions):
        section_id = disruption["section_id"]
        closure_start = disruption["start_minute"]
        closure_end = disruption["end_minute"]

        affected_movements = movements_by_section[section_id]

        for movement_index, movement in enumerate(
            affected_movements
        ):
            train_id = movement["train_id"]

            delay_var = delay_vars[train_id]

            movement_start = movement["departure"]
            movement_end = movement["arrival"]

            # The movement must be entirely before the closure
            # OR entirely after the closure.
            before_closure = model.NewBoolVar(
                f"disruption_{disruption_index}_"
                f"{section_id}_{movement_index}_before"
            )

            after_closure = model.NewBoolVar(
                f"disruption_{disruption_index}_"
                f"{section_id}_{movement_index}_after"
            )

            # At least one of these alternatives must hold.
            model.Add(
                before_closure + after_closure >= 1
            )

            # Option 1: movement finishes at/before closure start.
            model.Add(
                movement_end + delay_var <= closure_start
            ).OnlyEnforceIf(before_closure)

            # Option 2: movement starts at/after closure end.
            model.Add(
                movement_start + delay_var >= closure_end
            ).OnlyEnforceIf(after_closure)

    # ---------------------------------------------------------
    # 8. Objective: minimize total added departure delay
    # ---------------------------------------------------------

    model.Minimize(
        sum(delay_vars.values())
    )

    # ---------------------------------------------------------
    # 9. Solve model
    # ---------------------------------------------------------

    solver = cp_model.CpSolver()

    solver.parameters.max_time_in_seconds = float(
        time_limit_seconds
    )

    solver.parameters.num_search_workers = 1

    status = solver.Solve(model)

    status_name = solver.StatusName(status)

    if status not in (
        cp_model.OPTIMAL,
        cp_model.FEASIBLE,
    ):
        return {
            "status": status_name,
            "optimized_trains": [],
            "total_added_departure_delay_minutes": None,
            "message": (
                "No feasible schedule was found under the "
                "configured delay limit and constraints."
            ),
        }

    # ---------------------------------------------------------
    # 10. Build optimized schedule
    # ---------------------------------------------------------

    optimized_trains = []
    total_added_delay = 0

    for train in baseline_trains:
        train_id = train["train_id"]

        added_delay = solver.Value(
            delay_vars[train_id]
        )

        total_added_delay += added_delay

        optimized_train = {
            **train,
            "added_departure_delay_minutes": added_delay,
            "scheduled_departure": (
                train["scheduled_departure"] + added_delay
            ),
            "simulated_arrival": (
                train["simulated_arrival"] + added_delay
            ),
            "movements": [],
        }

        for movement in train.get("movements", []):
            optimized_movement = {
                **movement,
                "departure": (
                    movement["departure"] + added_delay
                ),
                "arrival": (
                    movement["arrival"] + added_delay
                ),
            }

            optimized_train["movements"].append(
                optimized_movement
            )

        optimized_trains.append(optimized_train)

    # ---------------------------------------------------------
    # 11. Return result
    # ---------------------------------------------------------

    return {
        "status": status_name,
        "optimized_trains": optimized_trains,
        "total_added_departure_delay_minutes": (
            total_added_delay
        ),
        "message": (
            "A feasible optimized schedule was found."
            if status == cp_model.OPTIMAL
            else (
                "A feasible schedule was found, but optimality "
                "was not proven within the time limit."
            )
        ),
    }