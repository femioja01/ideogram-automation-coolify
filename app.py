"""
FastAPI Control Center Backend for Ideogram Automation
------------------------------------------------------
Serves a dashboard UI, manages prompts.csv, executes background pipeline tasks,
and streams real-time logs to the browser via WebSocket.
"""

import os
import json
import asyncio
import threading
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, Request, HTTPException, Depends, status, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import main_drission as engine

app = FastAPI(title="Ideogram Automation Control Center")

# Mount static and output directories
BASE_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount("/output_images", StaticFiles(directory=engine.OUTPUT_DIR), name="output_images")

templates = Jinja2Templates(directory=BASE_DIR / "templates")

# ── App State ─────────────────────────────────────────────────────────────────

class GlobalState:
    def __init__(self):
        self.status = "Idle" # Idle, Running, Stopping
        self.logs: List[str] = []
        self.active_websockets: List[WebSocket] = []
        self.cancel_requested = False
        self.worker_thread: Optional[threading.Thread] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None

state = GlobalState()

def broadcast_log(message: str):
    """Callback function passed to pipeline to stream logs live."""
    formatted_msg = f"{message}"
    state.logs.append(formatted_msg)
    if len(state.logs) > 500:
        state.logs.pop(0)

    print(formatted_msg, flush=True)

    if state.loop and state.active_websockets:
        asyncio.run_coroutine_threadsafe(_async_broadcast(formatted_msg), state.loop)

async def _async_broadcast(message: str):
    payload = json.dumps({"type": "log", "message": message, "status": state.status})
    disconnected = []
    for ws in state.active_websockets:
        try:
            await ws.send_text(payload)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        if ws in state.active_websockets:
            state.active_websockets.remove(ws)

# ── Authentication Helper ────────────────(Disabled for simple local use)
def check_auth():
    return True

# ── Background Worker ─────────────────────────────────────────────────────────

def run_worker_task(single_row_index: Optional[int] = None):
    state.status = "Running"
    state.cancel_requested = False
    broadcast_log("[SYSTEM] Starting automation task...")

    try:
        engine.run_pipeline_sync(
            log_callback=broadcast_log,
            cancel_check=lambda: state.cancel_requested,
            single_row_index=single_row_index
        )
    except Exception as e:
        broadcast_log(f"[ERROR] Pipeline error: {e}")
    finally:
        state.status = "Idle"
        state.cancel_requested = False
        broadcast_log("[SYSTEM] Task finished. Status set to Idle.")

def run_login_task():
    state.status = "Running"
    broadcast_log("[SYSTEM] Launching Ideogram interactive login in Chrome...")
    try:
        engine.login_and_save_session(log_fn=broadcast_log)
        broadcast_log("[SYSTEM] Login Chrome session ready.")
    except Exception as e:
        broadcast_log(f"[ERROR] Login error: {e}")
    finally:
        state.status = "Idle"

# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class PromptAddRequest(BaseModel):
    prompt: str

class PromptUpdateRequest(BaseModel):
    id: int
    prompt: Optional[str] = None
    status: Optional[str] = None

class PromptDeleteRequest(BaseModel):
    id: int

class PromptBulkDeleteRequest(BaseModel):
    ids: list[int]

class SingleRunRequest(BaseModel):
    id: int

class SettingsUpdateRequest(BaseModel):
    REPLICATE_API_TOKEN: Optional[str] = None
    SCORE_THRESHOLD: Optional[int] = None
    MAX_RETRIES: Optional[int] = None
    CLIPROXY_API_KEY: Optional[str] = None
    CLIPROXY_BASE_URL: Optional[str] = None
    CLIPROXY_MODEL: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None

@app.on_event("startup")
async def startup_event():
    state.loop = asyncio.get_running_loop()

@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request, authenticated: bool = Depends(check_auth)):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/status")
async def get_status(authenticated: bool = Depends(check_auth)):
    rows = engine.read_prompts_csv()
    total = len(rows)
    done = sum(1 for r in rows if r.get("status") == "Done")
    failed = sum(1 for r in rows if r.get("status") == "Failed")
    pending = total - done - failed

    image_files = list(engine.OUTPUT_DIR.glob("*.jpg")) + list(engine.OUTPUT_DIR.glob("*.png"))

    return {
        "status": state.status,
        "total_prompts": total,
        "done_count": done,
        "pending_count": pending,
        "failed_count": failed,
        "image_count": len(image_files)
    }

@app.get("/api/prompts")
async def get_prompts(authenticated: bool = Depends(check_auth)):
    return engine.read_prompts_csv()

@app.post("/api/prompts/add")
async def add_prompt(req: PromptAddRequest, authenticated: bool = Depends(check_auth)):
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt text cannot be empty.")
    success = engine.add_prompt_csv(req.prompt)
    return {"success": success, "prompts": engine.read_prompts_csv()}

@app.post("/api/prompts/update")
async def update_prompt(req: PromptUpdateRequest, authenticated: bool = Depends(check_auth)):
    success = engine.update_prompt_csv(req.id, prompt=req.prompt, status=req.status)
    return {"success": success, "prompts": engine.read_prompts_csv()}

@app.post("/api/prompts/delete")
async def delete_prompt(req: PromptDeleteRequest, authenticated: bool = Depends(check_auth)):
    success = engine.delete_prompt_csv(req.id)
    return {"success": success, "prompts": engine.read_prompts_csv()}

@app.post("/api/prompts/delete-bulk")
async def delete_prompts_bulk(req: PromptBulkDeleteRequest, authenticated: bool = Depends(check_auth)):
    count = engine.delete_multiple_prompts_csv(req.ids)
    broadcast_log(f"[SYSTEM] Deleted {count} selected prompt(s) from database.")
    return {"status": "success", "deleted_count": count, "prompts": engine.read_prompts_csv()}

@app.post("/api/prompts/clear-all")
async def clear_all_prompts(authenticated: bool = Depends(check_auth)):
    engine.clear_all_prompts_csv()
    broadcast_log("[SYSTEM] Cleared all prompts from database.")
    return {"status": "success", "prompts": []}

@app.post("/api/prompts/reset-failed")
async def reset_failed_prompts(authenticated: bool = Depends(check_auth)):
    reset_count = engine.reset_failed_prompts()
    broadcast_log(f"[SYSTEM] Reset {reset_count} failed prompt(s) back to pending.")
    return {"reset_count": reset_count}

@app.post("/api/run")
async def trigger_run_all(authenticated: bool = Depends(check_auth)):
    if state.status == "Running":
        return JSONResponse({"status": "already_running", "message": "Automation is already running."})
    state.worker_thread = threading.Thread(target=run_worker_task, daemon=True)
    state.worker_thread.start()
    return {"status": "started", "message": "Batch automation started."}

@app.post("/api/run-single")
async def trigger_run_single(req: SingleRunRequest, authenticated: bool = Depends(check_auth)):
    if state.status == "Running":
        return JSONResponse({"status": "already_running", "message": "Automation is already running."})
    state.worker_thread = threading.Thread(target=run_worker_task, args=(req.id,), daemon=True)
    state.worker_thread.start()
    return {"status": "started", "message": f"Single run started for prompt #{req.id + 1}."}

@app.post("/api/stop")
async def trigger_stop(authenticated: bool = Depends(check_auth)):
    if state.status != "Running":
        return {"status": "not_running", "message": "No task is currently running."}
    state.cancel_requested = True
    state.status = "Stopping"
    broadcast_log("[SYSTEM] Cancellation requested by user...")
    return {"status": "stopping", "message": "Cancellation request sent."}

@app.post("/api/login")
async def trigger_login(authenticated: bool = Depends(check_auth)):
    if state.status == "Running":
        return JSONResponse({"status": "already_running", "message": "Automation is currently running."})
    state.worker_thread = threading.Thread(target=run_login_task, daemon=True)
    state.worker_thread.start()
    return {"status": "started", "message": "Chrome login session window opened."}

@app.get("/api/gallery")
async def get_gallery(authenticated: bool = Depends(check_auth)):
    prompts = engine.read_prompts_csv()
    prompt_by_filename = {p["filename"]: p for p in prompts if p["filename"]}
    images = []
    for file in sorted(engine.OUTPUT_DIR.glob("*.*"), key=os.path.getmtime, reverse=True):
        if file.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]:
            csv_meta = prompt_by_filename.get(file.name, {})
            images.append({
                "filename": file.name,
                "url": f"/output_images/{file.name}",
                "size_kb": round(file.stat().st_size / 1024, 1),
                "modified": file.stat().st_mtime,
                "prompt": csv_meta.get("prompt", file.stem),
                "score": csv_meta.get("score", "N/A"),
                "date": csv_meta.get("date", "")
            })
    return images

@app.get("/api/settings")
async def get_settings(authenticated: bool = Depends(check_auth)):
    return engine.load_settings()

@app.post("/api/settings")
async def update_settings(req: SettingsUpdateRequest, authenticated: bool = Depends(check_auth)):
    new_data = req.dict(exclude_unset=True)
    updated = engine.save_settings(new_data)
    broadcast_log(f"[SYSTEM] Settings updated: {updated}")
    return updated

@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await websocket.accept()
    state.active_websockets.append(websocket)
    try:
        await websocket.send_text(json.dumps({
            "type": "history",
            "logs": state.logs,
            "status": state.status
        }))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in state.active_websockets:
            state.active_websockets.remove(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
