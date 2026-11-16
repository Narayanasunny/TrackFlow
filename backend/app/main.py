
import logging
import os

from dotenv import load_dotenv

load_dotenv()
from contextlib import asynccontextmanager

from backend.app.agents.trackflow_graph import build_trackflow_graph

from backend.app.agents.traffic_analysis_agent import analyze_traffic

from backend.app.schedule_validator import validate_optimized_schedule

from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from uuid import UUID, uuid4
from langchain_core.messages import HumanMessage
from starlette.exceptions import HTTPException as StarletteHTTPException

from fastapi.middleware.cors import CORSMiddleware

from backend.app.agents.explainability_agent import (
    explain_optimization,
    analyze_what_if,
)


from backend.app.simulation.engine import (
    run_baseline_simulation,
    load_dataset,
    detect_track_conflicts,
)
from backend.app.optimization.optimizer import optimize_departures

from backend.app.agents.dynamic_rescheduling_agent import (
    run_dynamic_rescheduling,
    DynamicReschedulingError,
)


#--------------------------------------------------


# --------------------------------------------------
# Logging configuration
# --------------------------------------------------

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger("trackflow")


# --------------------------------------------------
# Response models
# --------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    application: str
    version: str
    
    
class DisruptionRequest(BaseModel):
    train_id: str = Field(min_length=1)
    delay_minutes: int = Field(ge=1, le=120)
    
    
class TrackClosureRequest(BaseModel):
    section_id: str
    start_minute: int
    end_minute: int


class AgentChatRequest(BaseModel):
    user_request: str = Field(min_length=3, max_length=2000)
    # Reuse this UUID for every message in one browser conversation.
    session_id: UUID | None = None


# --------------------------------------------------
# Application lifecycle
# --------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("TrackFlow backend is starting.")

    try:
        yield
    finally:
        logger.info("TrackFlow backend is shutting down.")


# --------------------------------------------------
# FastAPI application
# --------------------------------------------------

app = FastAPI(
    title="TrackFlow API",
    description=(
        "Railway traffic throughput optimization and "
        "decision-support platform."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# --------------------------------------------------
# CORS configuration for React frontend
# --------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------
# Global exception handlers
# --------------------------------------------------

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    logger.warning(
        "Invalid request: method=%s path=%s",
        request.method,
        request.url.path,
    )

    return JSONResponse(
        status_code=422,
        content={
            "error": "VALIDATION_ERROR",
            "message": "The request contains invalid data.",
            "details": exc.errors(),
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "HTTP_ERROR",
            "message": str(exc.detail),
        },
        headers=exc.headers,
    )


@app.exception_handler(Exception)
async def unexpected_exception_handler(
    request: Request,
    exc: Exception,
):
    logger.exception(
        "Unexpected error: method=%s path=%s",
        request.method,
        request.url.path,
    )

    return JSONResponse(
        status_code=500,
        content={
            "error": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected server error occurred.",
        },
    )


# --------------------------------------------------
# Routes
# --------------------------------------------------

@app.get("/", tags=["General"])
async def root():
    return {
        "application": "TrackFlow",
        "message": "Railway traffic optimization platform",
        "status": "running",
        "documentation": "/docs",
    }


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["Health"],
)
async def health_check():
    return HealthResponse(
        status="healthy",
        application="TrackFlow",
        version=app.version,
    )


# --------------------------------------------------
# Simulation and optimization routes
# --------------------------------------------------

@app.get("/api/simulation/baseline", tags=["Simulation"])
async def baseline_simulation():
    try:
        result = run_baseline_simulation()
        return result

    except Exception as exc:
        logger.exception("Baseline simulation failed.")
        raise HTTPException(
            status_code=500,
            detail="Baseline simulation failed.",
        ) from exc

#-------------------------------------------------


@app.get("/api/optimization", tags=["Optimization"])
async def optimized_simulation():
    try:
        # 1. Run the original baseline simulation
        baseline = run_baseline_simulation()

        # 2. Load railway network data
        dataset = load_dataset()

        # 3. Run the actual dynamic rescheduling algorithm
        #    directly, without asking the LLM to select a tool.
        rescheduling = run_dynamic_rescheduling(
            baseline_trains=baseline["trains"],
            track_sections=dataset["track_sections"],
            validate_schedule=validate_optimized_schedule,
        )

        # 4. Check whether an optimized schedule was generated
        if not rescheduling.get("optimized_trains"):
            raise HTTPException(
                status_code=422,
                detail=rescheduling.get(
                    "message",
                    "No feasible optimized schedule was found.",
                ),
            )

        validation = rescheduling.get("validation") or {}
        remaining_conflicts = (
            rescheduling.get("remaining_conflicts") or []
        )

        # 5. Return the optimization results to React
        return {
            "status": rescheduling.get("status"),
            "baseline_conflicts": baseline.get(
                "conflict_count",
                len(baseline.get("conflicts") or []),
            ),
            "optimized_conflicts": validation.get(
                "conflict_count",
                len(remaining_conflicts),
            ),
            "total_added_departure_delay_minutes": (
                rescheduling.get(
                    "total_added_departure_delay_minutes"
                )
            ),
            "optimized_trains": rescheduling["optimized_trains"],
            "remaining_conflicts": remaining_conflicts,
            "validation": validation,
            "recommendations": rescheduling.get(
                "recommendations", []
            ),
            "limitations": rescheduling.get(
                "limitations", []
            ),
            "traffic_analysis": {},
            "explanation": {},
            "final_response": (
                "Train schedule optimization completed."
            ),
        }

    except HTTPException:
        raise

    except DynamicReschedulingError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        logger.exception("Optimization endpoint failed.")
        raise HTTPException(
            status_code=500,
            detail=f"Optimization failed: {exc}",
        ) from exc


#---------------------------------------------
@app.get("/api/track-sections", tags=["Simulation"])
async def get_track_sections():
    try:
        dataset = load_dataset()

        return {
            "track_sections": dataset["track_sections"]
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load track sections: {exc}",
        )

#--------------------------------------------------
@app.post("/api/simulation/disruption", tags=["Simulation"])
async def simulate_disruption(request: DisruptionRequest):
    """
    Simulate an extra departure delay for one train,
    then optimize and validate the disrupted schedule.
    """
    try:
        # Load the original baseline and track dataset.
        baseline = run_baseline_simulation()
        dataset = load_dataset()
        original_trains = baseline["trains"]

        # Find the requested train.
        selected_train = next(
            (
                train
                for train in original_trains
                if train["train_id"] == request.train_id
            ),
            None,
        )

        if selected_train is None:
            raise HTTPException(
                status_code=404,
                detail=f"Train {request.train_id} was not found.",
            )

        if (
            not isinstance(request.delay_minutes, int)
            or isinstance(request.delay_minutes, bool)
            or request.delay_minutes < 0
        ):
            raise HTTPException(
                status_code=422,
                detail="Delay minutes must be a non-negative integer.",
            )

        # Copy the baseline so the original simulation remains unchanged.
        disrupted_trains = []

        for train in original_trains:
            updated = {
                **train,
                "movements": [
                    dict(movement)
                    for movement in train.get("movements", [])
                ],
            }

            if train["train_id"] == request.train_id:
                extra_delay = request.delay_minutes

                updated["scheduled_departure"] += extra_delay
                updated["simulated_arrival"] += extra_delay

                updated["delay_minutes"] = max(
                    0,
                    updated["simulated_arrival"]
                    - updated["target_arrival"],
                )

                for movement in updated["movements"]:
                    movement["departure"] += extra_delay
                    movement["arrival"] += extra_delay

            disrupted_trains.append(updated)

        # Detect conflicts after applying the disruption.
        disrupted_conflicts = detect_track_conflicts(
            disrupted_trains,
            dataset["track_sections"],
        )

        # Optimize the disrupted schedule.
        result = optimize_departures(
            disrupted_trains,
            dataset["track_sections"],
        )

        if not result.get("optimized_trains"):
            raise HTTPException(
                status_code=422,
                detail=result.get(
                    "message",
                    "No feasible schedule was found after the disruption.",
                ),
            )

        optimized_trains = result["optimized_trains"]

        # Validate the optimized schedule.
        validation = validate_optimized_schedule(
            disrupted_trains,
            optimized_trains,
            dataset["track_sections"],
        )

        # Explain the differences between baseline and optimized schedules.
        explanation = explain_optimization(
            baseline_trains=disrupted_trains,
            optimized_trains=optimized_trains,
            baseline_conflicts=disrupted_conflicts,
            remaining_conflicts=validation["conflicts"],
        )

        # Compare baseline, disrupted, and optimized scenarios.
        what_if_analysis = analyze_what_if(
            baseline_trains=original_trains,
            disrupted_trains=disrupted_trains,
            optimized_trains=optimized_trains,
            baseline_conflicts=baseline.get("conflicts", []),
            disrupted_conflicts=disrupted_conflicts,
            optimized_conflicts=validation["conflicts"],
        )

        return {
            "scenario_type": "synthetic_departure_delay",
            "disrupted_train_id": request.train_id,
            "disruption_delay_minutes": request.delay_minutes,
            "baseline_conflicts": baseline["conflict_count"],
            "disrupted_conflicts": len(disrupted_conflicts),
            "optimized_conflicts": validation["conflict_count"],
            "total_added_departure_delay_minutes": (
                result["total_added_departure_delay_minutes"]
            ),
            "status": result["status"],
            "disrupted_trains": disrupted_trains,
            "optimized_trains": optimized_trains,
            "disruption_conflict_details": disrupted_conflicts,
            "remaining_conflicts": validation["conflicts"],
            "validation": {
                "passed": validation["passed"],
                "integrity_errors": validation["integrity_errors"],
                "conflict_count": validation["conflict_count"],
            },
            "explanation": explanation,
            "what_if_analysis": what_if_analysis,
        }

    except HTTPException:
        raise

    except Exception as exc:
        logger.exception("Disruption simulation failed.")
        raise HTTPException(
            status_code=500,
            detail="Disruption simulation failed.",
        ) from exc
        
#_-------------------------------------------------

@app.post("/api/simulation/track-closure", tags=["Simulation"])
async def simulate_track_closure(request: TrackClosureRequest):
    """
    Simulate a temporary track closure and optimize the schedule.
    """
    try:
        # Validate closure time.
        if (
            request.start_minute < 0
            or request.end_minute <= request.start_minute
        ):
            raise HTTPException(
                status_code=422,
                detail=(
                    "Closure start must be non-negative and "
                    "end must be greater than start."
                ),
            )

        # Load the baseline schedule and track dataset.
        baseline = run_baseline_simulation()
        dataset = load_dataset()

        baseline_trains = baseline["trains"]
        track_sections = dataset["track_sections"]

        # Check whether the requested track section exists.
        section_exists = any(
            section.get("section_id") == request.section_id
            for section in track_sections
        )

        if not section_exists:
            raise HTTPException(
                status_code=404,
                detail=f"Track section {request.section_id} was not found.",
            )

        # Create the closure definition.
        disruptions = [
            {
                "section_id": request.section_id,
                "start_minute": request.start_minute,
                "end_minute": request.end_minute,
            }
        ]

        # Find conflicts in the baseline schedule.
        baseline_conflicts = detect_track_conflicts(
            baseline_trains,
            track_sections,
        )

        # Run the optimizer with the track closure.
        result = optimize_departures(
            baseline_trains=baseline_trains,
            track_sections=track_sections,
            disruptions=disruptions,
        )

        optimized_trains = result.get("optimized_trains", [])

        if not optimized_trains:
            raise HTTPException(
                status_code=422,
                detail=result.get(
                    "message",
                    "No feasible schedule was found.",
                ),
            )

        # Validate the optimized schedule.
        validation = validate_optimized_schedule(
            baseline_trains,
            optimized_trains,
            track_sections,
            disruptions=disruptions,
        )

        # Explain the optimization result.
        explanation = explain_optimization(
            baseline_trains=baseline_trains,
            optimized_trains=optimized_trains,
            baseline_conflicts=baseline_conflicts,
            remaining_conflicts=validation["conflicts"],
        )

        return {
            "scenario_type": "temporary_track_closure",
            "disruption": disruptions[0],
            "baseline_conflict_count": len(baseline_conflicts),
            "optimized_conflict_count": validation["conflict_count"],
            "total_added_departure_delay_minutes": (
                result["total_added_departure_delay_minutes"]
            ),
            "status": result["status"],
            "optimized_trains": optimized_trains,
            "remaining_conflicts": validation["conflicts"],
            "validation": {
                "passed": validation["passed"],
                "integrity_errors": validation["integrity_errors"],
                "conflict_count": validation["conflict_count"],
                "disruptions_checked": validation.get(
                    "disruptions_checked",
                    len(disruptions),
                ),
            },
            "explanation": explanation,
        }

    except HTTPException:
        raise

    except Exception as exc:
        logger.exception("Track closure simulation failed.")
        raise HTTPException(
            status_code=500,
            detail="Track closure simulation failed.",
        ) from exc
        
        
#--------------------------------------------------
@app.get("/api/agents/dynamic-rescheduling", tags=["AI Agents"])
async def dynamic_rescheduling():
    try:
        baseline = run_baseline_simulation()
        dataset = load_dataset()

        return run_dynamic_rescheduling(
            baseline_trains=baseline["trains"],
            track_sections=dataset["track_sections"],
            validate_schedule=validate_optimized_schedule,
        )

    except DynamicReschedulingError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except Exception:
        logger.exception("Dynamic rescheduling agent failed.")
        raise HTTPException(
            status_code=500,
            detail="Dynamic rescheduling failed. Check the backend logs.",
        )
        

#--------------------------------------------------
@app.get("/api/agents/explainability", tags=["AI Agents"])
async def explainability():
    try:
        baseline = run_baseline_simulation()
        dataset = load_dataset()

        result = run_dynamic_rescheduling(
            baseline_trains=baseline["trains"],
            track_sections=dataset["track_sections"],
            validate_schedule=validate_optimized_schedule,
        )

        if not result.get("optimized_trains"):
            raise HTTPException(
                status_code=422,
                detail=result.get(
                    "message",
                    "No feasible optimized schedule was found.",
                ),
            )

        return explain_optimization(
            baseline_trains=baseline["trains"],
            optimized_trains=result["optimized_trains"],
            baseline_conflicts=baseline.get("conflicts", []),
            remaining_conflicts=result["remaining_conflicts"],
        )

    except DynamicReschedulingError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except Exception:
        logger.exception("Explainability agent failed.")
        raise HTTPException(
            status_code=500,
            detail="Explainability failed. Check the backend logs.",
        )

# --------------------------------------------------
# Traffic Analysis Agent
# --------------------------------------------------

@app.get("/api/agents/traffic-analysis", tags=["AI Agents"])
async def traffic_analysis():
    try:
        return analyze_traffic()
    except Exception:
        logger.exception("Traffic analysis agent failed.")
        raise HTTPException(
            status_code=500,
            detail="Traffic analysis failed. Check the backend logs.",
        )


# --------------------------------------------------
# Natural-language Agentic AI endpoint
# --------------------------------------------------

@app.post("/api/agent/chat", tags=["Agentic AI"])
async def trackflow_agent_chat(request: AgentChatRequest):
    """Process a request in a session-aware LangGraph conversation thread."""
    try:
        session_id = str(request.session_id or uuid4())
        baseline = run_baseline_simulation()
        dataset = load_dataset()
        graph = build_trackflow_graph()

        # add_messages appends this turn's HumanMessage to the checkpointed
        # conversation. Current-turn outputs are reset; last_* context persists.
        initial_state = {
            "user_request": request.user_request.strip(),
            "messages": [HumanMessage(content=request.user_request.strip())],
            "baseline_trains": baseline["trains"],
            "track_sections": dataset["track_sections"],
            "traffic_analysis": {},
            "rescheduling_result": {},
            "explanation": {},
            "disruptions": [],
            "tools_used": [],
            "error": "",
        }
        config = {"configurable": {"thread_id": session_id}}
        result = graph.invoke(initial_state, config=config)

        return {
            "session_id": session_id,
            "user_request": request.user_request.strip(),
            "final_response": result.get(
                "final_response",
                "The TrackFlow agent completed the request but did not return a text explanation.",
            ),
            # Current-turn fields only; old tool output is retained internally
            # for follow-up reasoning and is not misreported as newly executed.
            "traffic_analysis": result.get("traffic_analysis") or {},
            "optimization": result.get("rescheduling_result") or {},
            "explanation": result.get("explanation") or {},
            "disruptions": result.get("disruptions") or [],
            "tools_used": result.get("tools_used") or [],
            "error": result.get("error") or None,
            "memory": {
                "enabled": True,
                "type": "in_memory_session",
                "note": (
                    "Conversation memory remains available while the backend process "
                    "is running. Restarting the backend clears in-memory sessions."
                ),
            },
        }

    except DynamicReschedulingError as exc:
        logger.warning("Agent rescheduling failed: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("TrackFlow Agentic AI request failed.")
        raise HTTPException(
            status_code=500,
            detail="The TrackFlow agent could not process the request. Check the backend logs.",
        ) from exc
