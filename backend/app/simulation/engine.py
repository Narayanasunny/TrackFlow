
import json
import logging
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)

# Project root: TrackFlow/
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data" / "raw"


class SimulationError(Exception):
    """Raised when simulation data or operations are invalid."""


def load_json_file(file_path: Path) -> dict[str, Any]:
    """Load and validate a JSON file containing an object."""
    try:
        with file_path.open("r", encoding="utf-8") as file:
            data = json.load(file)

    except FileNotFoundError as exc:
        raise SimulationError(
            f"Required dataset not found: {file_path}"
        ) from exc

    except json.JSONDecodeError as exc:
        raise SimulationError(
            f"Invalid JSON in {file_path.name}: {exc}"
        ) from exc

    except OSError as exc:
        raise SimulationError(
            f"Could not read {file_path.name}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise SimulationError(
            f"Expected a JSON object in {file_path.name}."
        )

    return data


def load_dataset() -> dict[str, list[dict[str, Any]]]:
    """Load the station, track-section, and train datasets."""
    files = {
        "stations": DATA_DIR / "stations.json",
        "track_sections": DATA_DIR / "track_sections.json",
        "trains": DATA_DIR / "trains.json",
    }

    dataset: dict[str, list[dict[str, Any]]] = {}

    for name, file_path in files.items():
        content = load_json_file(file_path)
        records = content.get(name)

        if not isinstance(records, list):
            raise SimulationError(
                f"Expected a list under '{name}' in {file_path.name}."
            )

        if not all(isinstance(item, dict) for item in records):
            raise SimulationError(
                f"Every entry in {file_path.name} must be an object."
            )

        dataset[name] = records

    logger.info(
        "Loaded %d stations, %d track sections, and %d trains.",
        len(dataset["stations"]),
        len(dataset["track_sections"]),
        len(dataset["trains"]),
    )

    return dataset


def build_track_lookup(
    track_sections: list[dict[str, Any]],
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """
    Map each station pair to all connecting track sections.

    Connections are registered in both directions. Parallel sections
    remain separate entries and are not overwritten.
    """
    lookup: dict[tuple[str, str], list[dict[str, Any]]] = {}
    seen_section_ids: set[str] = set()

    for section in track_sections:
        section_id = section.get("section_id")
        start = section.get("from_station")
        end = section.get("to_station")
        travel_time = section.get("travel_time_minutes")
        headway = section.get("minimum_headway_minutes")

        if not isinstance(section_id, str) or not section_id:
            raise SimulationError("A track section has an invalid ID.")

        if section_id in seen_section_ids:
            raise SimulationError(
                f"Duplicate track section ID: {section_id}."
            )
        seen_section_ids.add(section_id)

        if (
            not isinstance(start, str)
            or not start
            or not isinstance(end, str)
            or not end
            or start == end
        ):
            raise SimulationError(
                f"Invalid station endpoints in section {section_id}."
            )

        if (
            not isinstance(travel_time, (int, float))
            or isinstance(travel_time, bool)
            or travel_time <= 0
        ):
            raise SimulationError(
                f"Section {section_id} has invalid travel time."
            )

        if (
            not isinstance(headway, (int, float))
            or isinstance(headway, bool)
            or headway < 0
        ):
            raise SimulationError(
                f"Section {section_id} has invalid minimum headway."
            )

        if not isinstance(section.get("available"), bool):
            raise SimulationError(
                f"Section {section_id} must have a boolean 'available' value."
            )

        track_type = section.get("track_type", "single")
        if not isinstance(track_type, str) or track_type.lower() not in {
            "single",
            "double",
        }:
            raise SimulationError(
                f"Section {section_id} has an unsupported track type."
            )

        lookup.setdefault((start, end), []).append(section)
        lookup.setdefault((end, start), []).append(section)

    return lookup


def simulate_train(
    train: dict[str, Any],
    track_lookup: dict[tuple[str, str], list[dict[str, Any]]],
) -> dict[str, Any]:
    """
    Calculate a baseline journey for one train.

    This baseline selects the first available matching section.
    It does not optimize routes or resolve conflicts.
    """
    train_id = train.get("train_id", "UNKNOWN")
    route = train.get("route")

    if not isinstance(route, list) or len(route) < 2:
        raise SimulationError(
            f"Train {train_id} must have at least two route stations."
        )

    if not all(isinstance(station, str) and station for station in route):
        raise SimulationError(
            f"Train {train_id} has an invalid route."
        )

    departure_time = train.get("scheduled_departure_minutes")

    if (
        not isinstance(departure_time, (int, float))
        or isinstance(departure_time, bool)
        or departure_time < 0
    ):
        raise SimulationError(
            f"Train {train_id} has an invalid scheduled departure."
        )

    current_time = departure_time
    movements: list[dict[str, Any]] = []

    for index in range(len(route) - 1):
        start = route[index]
        end = route[index + 1]

        candidate_sections = track_lookup.get((start, end), [])

        available_sections = [
            section
            for section in candidate_sections
            if section.get("available") is True
        ]

        if not available_sections:
            raise SimulationError(
                f"Train {train_id} has no available track section "
                f"connecting {start} and {end}."
            )

        # Temporary baseline policy: use the first available section.
        # A later optimizer will evaluate alternative sections.
        section = available_sections[0]

        movement_departure = current_time
        movement_arrival = (
            movement_departure + section["travel_time_minutes"]
        )

        movements.append({
            "section_id": section["section_id"],
            "track_type": section.get("track_type", "single").lower(),
            "from_station": start,
            "to_station": end,
            "departure": movement_departure,
            "arrival": movement_arrival,
        })

        current_time = movement_arrival

    target_arrival = train.get("target_arrival_minutes")

    if (
        not isinstance(target_arrival, (int, float))
        or isinstance(target_arrival, bool)
        or target_arrival < 0
    ):
        raise SimulationError(
            f"Train {train_id} has an invalid target arrival."
        )

    priority = train.get("priority")
    if (
        not isinstance(priority, int)
        or isinstance(priority, bool)
        or priority < 1
    ):
        raise SimulationError(
            f"Train {train_id} has an invalid priority."
        )

    return {
        "train_id": train_id,
        "train_name": train.get("train_name", train_id),
        "train_type": train.get("train_type", "unknown"),
        "priority": priority,
        "scheduled_departure": departure_time,
        "simulated_arrival": current_time,
        "target_arrival": target_arrival,
        "delay_minutes": max(0, current_time - target_arrival),
        "movements": movements,
    }


def detect_track_conflicts(
    trains: list[dict[str, Any]],
    track_sections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Detect preliminary track occupancy overlaps and headway violations.

    Self-comparisons are excluded. This is not a complete railway
    interlocking, signaling, or safety validation system.
    """
    conflicts: list[dict[str, Any]] = []

    section_lookup: dict[str, dict[str, Any]] = {}
    for section in track_sections:
        section_id = section.get("section_id")

        if not isinstance(section_id, str) or not section_id:
            raise SimulationError("A track section has an invalid ID.")

        if section_id in section_lookup:
            raise SimulationError(
                f"Duplicate track section ID: {section_id}."
            )

        section_lookup[section_id] = section

    movements_by_section: dict[str, list[dict[str, Any]]] = {}

    for train in trains:
        train_id = train.get("train_id", "UNKNOWN")
        movements = train.get("movements", [])

        if not isinstance(movements, list):
            raise SimulationError(
                f"Train {train_id} has invalid movement data."
            )

        for movement in movements:
            if not isinstance(movement, dict):
                raise SimulationError(
                    f"Train {train_id} has an invalid movement entry."
                )

            section_id = movement.get("section_id")

            if section_id not in section_lookup:
                raise SimulationError(
                    f"Train {train_id} references unknown section "
                    f"{section_id}."
                )

            start = movement.get("from_station")
            end = movement.get("to_station")
            departure = movement.get("departure")
            arrival = movement.get("arrival")

            if (
                not isinstance(start, str)
                or not isinstance(end, str)
                or start == end
            ):
                raise SimulationError(
                    f"Train {train_id} has invalid movement endpoints."
                )

            for field_name, value in (
                ("departure", departure),
                ("arrival", arrival),
            ):
                if (
                    not isinstance(value, (int, float))
                    or isinstance(value, bool)
                ):
                    raise SimulationError(
                        f"Train {train_id} has an invalid {field_name} time."
                    )

            if departure < 0 or arrival <= departure:
                raise SimulationError(
                    f"Train {train_id} has invalid movement times."
                )

            movements_by_section.setdefault(section_id, []).append({
                **movement,
                "train_id": train_id,
            })

    for section_id, section_movements in movements_by_section.items():
        section = section_lookup[section_id]
        headway = section.get("minimum_headway_minutes", 0)
        track_type = section.get("track_type", "single").lower()

        if (
            not isinstance(headway, (int, float))
            or isinstance(headway, bool)
            or headway < 0
        ):
            raise SimulationError(
                f"Section {section_id} has invalid minimum headway."
            )

        section_movements.sort(key=lambda item: item["departure"])

        for i, first in enumerate(section_movements):
            for second in section_movements[i + 1:]:
                # A train must never conflict with its own movement.
                if first["train_id"] == second["train_id"]:
                    continue

                same_direction = (
                    first["from_station"] == second["from_station"]
                    and first["to_station"] == second["to_station"]
                )

                # Simplified double-track assumption:
                # opposite directions use separate tracks.
                if track_type == "double" and not same_direction:
                    continue

                overlap = (
                    first["departure"] < second["arrival"]
                    and second["departure"] < first["arrival"]
                )

                if overlap:
                    conflicts.append({
                        "section_id": section_id,
                        "train_1": first["train_id"],
                        "train_2": second["train_id"],
                        "conflict_type": "overlapping_occupancy",
                        "train_1_direction": (
                            f"{first['from_station']}->{first['to_station']}"
                        ),
                        "train_2_direction": (
                            f"{second['from_station']}->{second['to_station']}"
                        ),
                        "train_1_departure": first["departure"],
                        "train_1_arrival": first["arrival"],
                        "train_2_departure": second["departure"],
                        "train_2_arrival": second["arrival"],
                        "overlap_start": max(
                            first["departure"], second["departure"]
                        ),
                        "overlap_end": min(
                            first["arrival"], second["arrival"]
                        ),
                        "message": (
                            f"{first['train_id']} and {second['train_id']} "
                            f"overlap on section {section_id}."
                        ),
                    })
                    continue

                # Headway is checked for movements in the same direction.
                if not same_direction:
                    continue

                if first["arrival"] <= second["departure"]:
                    earlier, later = first, second
                elif second["arrival"] <= first["departure"]:
                    earlier, later = second, first
                else:
                    continue

                separation = later["departure"] - earlier["arrival"]

                if separation < headway:
                    conflicts.append({
                        "section_id": section_id,
                        "train_1": earlier["train_id"],
                        "train_2": later["train_id"],
                        "conflict_type": "headway_violation",
                        "actual_separation_minutes": separation,
                        "required_headway_minutes": headway,
                        "message": (
                            f"{earlier['train_id']} and {later['train_id']} "
                            f"have {separation} minutes of separation on "
                            f"{section_id}; {headway} minutes are required."
                        ),
                    })

    return conflicts


def run_baseline_simulation() -> dict[str, Any]:
    """Run the baseline simulation and report preliminary conflicts."""
    dataset = load_dataset()
    track_lookup = build_track_lookup(dataset["track_sections"])

    train_ids = [
        train.get("train_id")
        for train in dataset["trains"]
    ]

    if any(not isinstance(train_id, str) or not train_id for train_id in train_ids):
        raise SimulationError("Every train must have a valid train ID.")

    if len(train_ids) != len(set(train_ids)):
        raise SimulationError("Duplicate train IDs were found.")

    results = [
        simulate_train(train, track_lookup)
        for train in dataset["trains"]
    ]

    conflicts = detect_track_conflicts(
        results,
        dataset["track_sections"],
    )

    total_delay = sum(
        train_result["delay_minutes"]
        for train_result in results
    )

    return {
        "simulation_type": "baseline",
        "conflicts_resolved": False,
        "train_count": len(results),
        "total_delay_minutes": total_delay,
        "conflict_count": len(conflicts),
        "conflicts": conflicts,
        "trains": results,
    }


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s | %(message)s",
    )

    try:
        result = run_baseline_simulation()

        print("\nTRACKFLOW BASELINE SIMULATION")
        print("-" * 40)
        print(f"Trains simulated: {result['train_count']}")
        print(f"Total delay: {result['total_delay_minutes']} minutes")
        print(f"Detected conflicts: {result['conflict_count']}")
        print("Conflict resolution: Not yet implemented")

        for train_result in result["trains"]:
            print(
                f"{train_result['train_id']}: "
                f"arrival={train_result['simulated_arrival']} min, "
                f"delay={train_result['delay_minutes']} min"
            )

        if result["conflicts"]:
            print("\nDETECTED CONFLICTS")
            print("-" * 40)

            for conflict in result["conflicts"]:
                print(
                    f"[{conflict['conflict_type']}] "
                    f"{conflict['message']}"
                )
        else:
            print(
                "\nNo conflicts detected by the preliminary detector."
            )

        print("\nBaseline simulation completed successfully.")

    except SimulationError as exc:
        logger.error("Simulation failed: %s", exc)
        raise SystemExit(1)

    except Exception:
        logger.exception("Unexpected simulation error.")
        raise SystemExit(1)
