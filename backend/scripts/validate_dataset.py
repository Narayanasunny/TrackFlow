
import json
import logging
import sys
from pathlib import Path
from typing import Any


# Project paths
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "raw"

STATIONS_FILE = DATA_DIR / "stations.json"
SECTIONS_FILE = DATA_DIR / "track_sections.json"
TRAINS_FILE = DATA_DIR / "trains.json"

EXPECTED_TRAIN_COUNT = 10

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(message)s",
)

logger = logging.getLogger("trackflow.dataset_validator")


class DatasetValidationError(Exception):
    """Raised when the railway dataset is invalid."""


def load_json(file_path: Path) -> dict[str, Any]:
    """Load a JSON file and provide a useful error if it fails."""

    if not file_path.exists():
        raise DatasetValidationError(
            f"File not found: {file_path}"
        )

    try:
        with file_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as exc:
        raise DatasetValidationError(
            f"Invalid JSON in {file_path.name}: "
            f"line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    except OSError as exc:
        raise DatasetValidationError(
            f"Cannot read {file_path}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise DatasetValidationError(
            f"{file_path.name} must contain a JSON object."
        )

    logger.info("Valid JSON syntax: %s", file_path.name)
    return data


def require_list(data: dict, key: str, filename: str) -> list:
    """Ensure a required JSON property contains a list."""

    value = data.get(key)

    if not isinstance(value, list):
        raise DatasetValidationError(
            f"{filename}: '{key}' must be a JSON array."
        )

    return value


def check_unique_ids(
    records: list,
    id_field: str,
    filename: str,
) -> set[str]:
    """Check that each record has a unique, non-empty ID."""

    identifiers = []

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise DatasetValidationError(
                f"{filename}: record {index + 1} must be an object."
            )

        identifier = record.get(id_field)

        if not isinstance(identifier, str) or not identifier.strip():
            raise DatasetValidationError(
                f"{filename}: record {index + 1} "
                f"has a missing or invalid '{id_field}'."
            )

        identifiers.append(identifier)

    if len(identifiers) != len(set(identifiers)):
        duplicates = sorted(
            identifier
            for identifier in set(identifiers)
            if identifiers.count(identifier) > 1
        )
        raise DatasetValidationError(
            f"{filename}: duplicate {id_field}: {duplicates}"
        )

    return set(identifiers)


def validate_dataset() -> None:
    """Validate railway stations, sections, and train routes."""

    stations_data = load_json(STATIONS_FILE)
    sections_data = load_json(SECTIONS_FILE)
    trains_data = load_json(TRAINS_FILE)

    stations = require_list(
        stations_data, "stations", STATIONS_FILE.name
    )
    sections = require_list(
        sections_data, "track_sections", SECTIONS_FILE.name
    )
    trains = require_list(
        trains_data, "trains", TRAINS_FILE.name
    )

    # 1. Check unique station IDs.
    station_ids = check_unique_ids(
        stations, "station_id", STATIONS_FILE.name
    )

    if not station_ids:
        raise DatasetValidationError(
            "At least one station is required."
        )

    for station in stations:
        capacity = station.get("platform_capacity")

        if (
            not isinstance(capacity, int)
            or isinstance(capacity, bool)
            or capacity <= 0
        ):
            raise DatasetValidationError(
                f"Station {station['station_id']} "
                "must have a positive integer platform_capacity."
            )

    logger.info("Station IDs are unique: %d stations", len(stations))

    # 2. Check track section IDs and station references.
    section_ids = check_unique_ids(
        sections, "section_id", SECTIONS_FILE.name
    )

    connections = set()

    for section in sections:
        start = section.get("from_station")
        end = section.get("to_station")
        travel_time = section.get("travel_time_minutes")
        headway = section.get("minimum_headway_minutes")

        if start not in station_ids or end not in station_ids:
            raise DatasetValidationError(
                f"Section {section['section_id']} references "
                f"an unknown station: {start} -> {end}."
            )

        if start == end:
            raise DatasetValidationError(
                f"Section {section['section_id']} "
                "cannot connect a station to itself."
            )

        if (
            not isinstance(travel_time, (int, float))
            or isinstance(travel_time, bool)
            or travel_time <= 0
        ):
            raise DatasetValidationError(
                f"Section {section['section_id']} "
                "must have a positive travel time."
            )

        if (
            not isinstance(headway, (int, float))
            or isinstance(headway, bool)
            or headway < 0
        ):
            raise DatasetValidationError(
                f"Section {section['section_id']} "
                "must have a non-negative minimum headway."
            )

        # The initial model treats sections as bidirectional.
        # Parallel connections between the same stations are allowed.
        connections.add((start, end))
        connections.add((end, start))

    logger.info(
        "Track sections validated: %d sections",
        len(section_ids),
    )

    # 3. Check train IDs and the expected train count.
    check_unique_ids(trains, "train_id", TRAINS_FILE.name)

    if len(trains) != EXPECTED_TRAIN_COUNT:
        raise DatasetValidationError(
            f"Expected {EXPECTED_TRAIN_COUNT} trains, "
            f"but found {len(trains)}."
        )

    logger.info("Train count is correct: %d trains", len(trains))

    # 4. Check train routes and timing fields.
    for train in trains:
        train_id = train["train_id"]
        route = train.get("route")

        if not isinstance(route, list) or len(route) < 2:
            raise DatasetValidationError(
                f"Train {train_id} must have a route "
                "containing at least two stations."
            )

        if any(
            not isinstance(station_id, str)
            or station_id not in station_ids
            for station_id in route
        ):
            raise DatasetValidationError(
                f"Train {train_id} references an unknown station."
            )

        for start, end in zip(route, route[1:]):
            if (start, end) not in connections:
                raise DatasetValidationError(
                    f"Train {train_id} has no track connection "
                    f"for route segment {start} -> {end}."
                )

        departure = train.get("scheduled_departure_minutes")
        target = train.get("target_arrival_minutes")
        priority = train.get("priority")
        stopping_time = train.get("stopping_time_minutes")

        if (
            not isinstance(departure, (int, float))
            or isinstance(departure, bool)
            or departure < 0
        ):
            raise DatasetValidationError(
                f"Train {train_id} has an invalid departure time."
            )

        if (
            not isinstance(target, (int, float))
            or isinstance(target, bool)
            or target < departure
        ):
            raise DatasetValidationError(
                f"Train {train_id} has an invalid target arrival time."
            )

        if (
            not isinstance(priority, int)
            or isinstance(priority, bool)
            or priority not in (1, 2, 3)
        ):
            raise DatasetValidationError(
                f"Train {train_id} priority must be 1, 2, or 3."
            )

        if (
            not isinstance(stopping_time, (int, float))
            or isinstance(stopping_time, bool)
            or stopping_time < 0
        ):
            raise DatasetValidationError(
                f"Train {train_id} has an invalid stopping time."
            )

    logger.info("All train routes and timing fields are valid.")
    logger.info("All dataset checks passed successfully!")


if __name__ == "__main__":
    try:
        validate_dataset()
    except DatasetValidationError as exc:
        logger.error("DATASET VALIDATION FAILED: %s", exc)
        sys.exit(1)
    except Exception:
        logger.exception("Unexpected validation error.")
        sys.exit(1)
