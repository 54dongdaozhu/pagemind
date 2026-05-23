import asyncio
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","name":"%(name)s","message":"%(message)s"}',
)
logger = logging.getLogger(__name__)

_WORD_DIR = os.getenv("DOC_GEN_WORD_DIR", "/tmp/doc-gen")
Path(_WORD_DIR).mkdir(parents=True, exist_ok=True)

# In-memory task registry: task_id → {"state": ..., "queue": asyncio.Queue, "done": bool}
_tasks: dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm up graph on startup
    from agents.orchestrator import get_graph
    get_graph()
    yield


app = FastAPI(title="DocGen Multi-Agent Service", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Schemas ─────────────────────────────────────────────────────────────────


class GenerateRequest(BaseModel):
    topic: str
    requirements: str = ""
    user_id: str = "anonymous"
    user_profile: dict = {}


class ResumeRequest(BaseModel):
    decision: str  # "publish" | "revise"
    feedback: str = ""


# ─── Background graph runner ──────────────────────────────────────────────────


def _check_interrupted(graph, config: dict) -> tuple[bool, dict]:
    """Return (is_interrupted, interrupt_payload) by inspecting graph state tasks."""
    try:
        state_snapshot = graph.get_state(config)
        for task in state_snapshot.tasks:
            if getattr(task, "interrupts", None):
                payload = task.interrupts[0].value if task.interrupts else {}
                return True, payload
    except Exception:
        pass
    return False, {}


async def _run_graph(task_id: str, initial_state: dict) -> None:
    from agents.orchestrator import get_graph

    queue: asyncio.Queue = _tasks[task_id]["queue"]
    graph = get_graph()
    config = {"configurable": {"thread_id": task_id}}

    def _emit(msg: dict) -> None:
        queue.put_nowait(json.dumps(msg, ensure_ascii=False))

    try:
        _tasks[task_id]["status"] = "running"

        async for event in graph.astream(initial_state, config=config, stream_mode="values"):
            msgs = event.get("progress_messages", [])
            agent = event.get("current_agent", "")
            status = event.get("status", "running")

            for m in msgs[-1:]:  # only newest message per event to avoid duplicates
                _emit({"type": "progress", "agent": agent, "message": m})

            if status == "error":
                _emit({"type": "error", "message": event.get("error", "Unknown error")})
                _tasks[task_id]["status"] = "error"
                return

        # Check if graph is interrupted (waiting for human)
        interrupted, interrupt_payload = _check_interrupted(graph, config)
        if interrupted:
            state_snapshot = graph.get_state(config)
            current_state = state_snapshot.values
            draft_html = interrupt_payload.get("draft_html", "")
            draft_md = interrupt_payload.get("draft_markdown", current_state.get("draft", ""))
            _tasks[task_id]["status"] = "waiting_human"
            _tasks[task_id]["last_state"] = current_state
            _emit({"type": "human_interrupt", "draft_html": draft_html, "draft_markdown": draft_md})
            return

        # Graph completed
        final_state = graph.get_state(config).values
        _tasks[task_id]["status"] = "done"
        _tasks[task_id]["last_state"] = final_state
        _emit({
            "type": "complete",
            "html": final_state.get("html_content", ""),
            "word_url": f"/api/doc-gen/{task_id}/word" if final_state.get("word_filename") else None,
        })

    except Exception as e:
        logger.exception("Graph run failed task_id=%s", task_id)
        _tasks[task_id]["status"] = "error"
        _emit({"type": "error", "message": str(e)})
    finally:
        _tasks[task_id]["done"] = True


async def _resume_graph(task_id: str, decision: str, feedback: str) -> None:
    from agents.orchestrator import get_graph
    from langgraph.types import Command  # noqa: F401 used below

    queue: asyncio.Queue = _tasks[task_id]["queue"]
    graph = get_graph()
    config = {"configurable": {"thread_id": task_id}}

    def _emit(msg: dict) -> None:
        queue.put_nowait(json.dumps(msg, ensure_ascii=False))

    try:
        _tasks[task_id]["status"] = "running"

        async for event in graph.astream(
            Command(resume={"decision": decision, "feedback": feedback}),
            config=config,
            stream_mode="values",
        ):
            msgs = event.get("progress_messages", [])
            agent = event.get("current_agent", "")
            status = event.get("status", "running")

            for m in msgs[-1:]:
                _emit({"type": "progress", "agent": agent, "message": m})

            if status == "error":
                _emit({"type": "error", "message": event.get("error", "Unknown error")})
                _tasks[task_id]["status"] = "error"
                return

        final_state = graph.get_state(config).values
        _tasks[task_id]["status"] = "done"
        _tasks[task_id]["last_state"] = final_state
        _emit({
            "type": "complete",
            "html": final_state.get("html_content", ""),
            "word_url": f"/api/doc-gen/{task_id}/word" if final_state.get("word_filename") else None,
        })

    except Exception as e:
        logger.exception("Graph resume failed task_id=%s", task_id)
        _tasks[task_id]["status"] = "error"
        _emit({"type": "error", "message": str(e)})
    finally:
        _tasks[task_id]["done"] = True


# ─── Endpoints ────────────────────────────────────────────────────────────────


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/doc-gen/generate")
async def generate(req: GenerateRequest):
    task_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    _tasks[task_id] = {"queue": queue, "done": False, "status": "pending", "last_state": {}}

    initial_state = {
        "task_id": task_id,
        "user_id": req.user_id,
        "topic": req.topic,
        "requirements": req.requirements,
        "user_profile": req.user_profile or {},
        "search_queries": [],
        "web_results": [],
        "research_notes": "",
        "outline": [],
        "sections": {},
        "current_section": {},
        "draft": "",
        "review_feedback": "",
        "review_decision": "",
        "revision_count": 0,
        "human_feedback": "",
        "human_decision": "",
        "html_content": "",
        "word_filename": "",
        "status": "running",
        "current_agent": "",
        "progress_messages": [],
        "error": None,
    }

    asyncio.create_task(_run_graph(task_id, initial_state))
    return {"task_id": task_id}


@app.get("/api/doc-gen/{task_id}/stream")
async def stream(task_id: str):
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task = _tasks[task_id]

    async def _generate() -> AsyncGenerator[str, None]:
        queue: asyncio.Queue = task["queue"]
        while True:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=30)
                yield f"{msg}\n"
                if task.get("done") and queue.empty():
                    break
            except asyncio.TimeoutError:
                if task.get("done"):
                    break
                yield json.dumps({"type": "ping"}) + "\n"

    return StreamingResponse(
        _generate(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/doc-gen/{task_id}/resume")
async def resume(task_id: str, req: ResumeRequest):
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    if _tasks[task_id]["status"] != "waiting_human":
        raise HTTPException(status_code=409, detail="Task is not waiting for human input")

    _tasks[task_id]["done"] = False
    _tasks[task_id]["queue"] = asyncio.Queue()  # Fresh queue for continued stream
    asyncio.create_task(_resume_graph(task_id, req.decision, req.feedback))
    return {"status": "resumed"}


@app.get("/api/doc-gen/{task_id}/result")
async def get_result(task_id: str):
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    task = _tasks[task_id]
    state = task.get("last_state", {})
    return {
        "status": task["status"],
        "html": state.get("html_content", ""),
        "word_url": f"/api/doc-gen/{task_id}/word" if state.get("word_filename") else None,
    }


@app.get("/api/doc-gen/{task_id}/word")
async def download_word(task_id: str):
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    state = _tasks[task_id].get("last_state", {})
    word_path = state.get("word_filename", "")
    if not word_path or not os.path.exists(word_path):
        raise HTTPException(status_code=404, detail="Word file not available")
    topic = state.get("topic", "document")
    safe_name = "".join(c if c.isalnum() or c in "- _" else "_" for c in topic)
    return FileResponse(
        word_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"{safe_name}.docx",
    )


@app.delete("/api/doc-gen/{task_id}")
async def delete_task(task_id: str):
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    state = _tasks.pop(task_id, {}).get("last_state", {})
    word_path = state.get("word_filename", "")
    if word_path and os.path.exists(word_path):
        os.remove(word_path)
    return {"status": "deleted"}
