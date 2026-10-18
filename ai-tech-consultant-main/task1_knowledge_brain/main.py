
from contextlib import asynccontextmanager
import os
from fastapi import FastAPI, HTTPException

from task1_knowledge_brain.models import (
    AskRequest,
    AskResponse,
    SyncRequest,
)
from task1_knowledge_brain.crawler import sync_articles
from task1_knowledge_brain.knowledge import ask_knowledge_brain
from task1_knowledge_brain.database import (
    initialize_database,
    save_expert_feedback,
    get_expert_feedback,
    update_feedback_status,
    get_latest_ingestion_run,
)

scheduler = None


@asynccontextmanager
async def lifespan(_app):
    global scheduler
    initialize_database()
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        scheduler = BackgroundScheduler(timezone="UTC")
        scheduler.add_job(
            sync_articles,
            "interval",
            hours=24,
            id="daily-help-center-sync",
            replace_existing=True,
            kwargs={
                "max_pages": int(os.getenv("MAX_SYNC_PAGES", "500")),
                "delay_seconds": float(os.getenv("CRAWL_DELAY_SECONDS", "1.0")),
            },
        )
        scheduler.start()
    except ImportError:
        scheduler = None
    try:
        yield
    finally:
        if scheduler and scheduler.running:
            scheduler.shutdown(wait=False)


app = FastAPI(
    title="AI Tech Consultant - Knowledge Brain",
    description="Knowledge retrieval, article sync, and expert feedback API",
    version="1.0.0",
    lifespan=lifespan,
)

@app.get("/")
def root():
    return {
        "message": "AI Tech Consultant Knowledge Brain API is running",
        "docs": "/docs",
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.post("/query", response_model=AskResponse)
@app.post("/knowledge/ask", response_model=AskResponse)
def ask_question(request: AskRequest):
    try:
        return ask_knowledge_brain(
            request.question,
            history=[
                message.model_dump()
                for message in request.history
            ],
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Knowledge query failed: {str(exc)}",
        ) from exc


@app.post("/ingestion/run")
@app.post("/knowledge/sync")
def sync_knowledge(request: SyncRequest):
    try:
        return sync_articles(
            max_pages=request.max_pages,
            delay_seconds=request.delay_seconds,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Article sync failed: {str(exc)}",
        ) from exc


@app.post("/escalations")
@app.post("/knowledge/feedback")
def submit_expert_feedback(payload: dict):
    question = payload.get("question", "").strip()
    answer = payload.get("answer", "").strip()

    if not question or not answer:
        raise HTTPException(
            status_code=400,
            detail="Both question and answer are required.",
        )

    try:
        feedback_id = save_expert_feedback(question, answer)
        return {
            "message": "Expert feedback submitted for review",
            "id": feedback_id,
            "status": "pending",
        }
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not save expert feedback: {str(exc)}",
        ) from exc


@app.get("/escalations")
@app.get("/knowledge/feedback")
def list_pending_feedback():
    try:
        feedback = get_expert_feedback(status="pending")
        return {"feedback": [dict(item) for item in feedback]}
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not retrieve feedback: {str(exc)}",
        ) from exc


@app.patch("/escalations/{feedback_id}/resolve")
@app.patch("/knowledge/feedback/{feedback_id}")
def review_feedback(feedback_id: int, status: str):
    if status not in {"approved", "rejected"}:
        raise HTTPException(
            status_code=400,
            detail="Status must be 'approved' or 'rejected'.",
        )

    try:
        updated = update_feedback_status(feedback_id, status)

        if not updated:
            raise HTTPException(
                status_code=404,
                detail="Feedback record not found.",
            )

        return {
            "message": "Feedback review completed",
            "id": feedback_id,
            "status": status,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not update feedback: {str(exc)}",
        ) from exc


@app.get("/ingestion/status")
def ingestion_status():
    initialize_database()
    return {"latest_run": get_latest_ingestion_run()}


@app.get("/health/ready")
def readiness_check():
    initialize_database()
    return {"status": "ready", "database": "initialized"}
