import os
import sys
import asyncio
import threading
from collections import deque
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException, Depends, Security
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

import main_drission as engine

app = FastAPI(title="Ideogram Automation Control Center")

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
OUTPUT_DIR = engine.OUTPUT_DIR

TEMPLATES_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/output_images", StaticFiles(directory=str(OUTPUT_DIR)), name="output_images")

security = HTTPBasic(auto_error=False)
BASIC_AUTH_USER = os.getenv("BASIC_AUTH_USERNAME", "").strip()
BASIC_AUTH_PASS = os.getenv("BASIC_AUTH_PASSWORD", "").strip()

def check_auth(credentials: Optional[HTTPBasicCredentials] = Security(security)):
    if not BASIC_AUTH_USER or not BASIC_AUTH_PASS:
        return True
    if credentials and credentials.username == BASIC_AUTH_USER and credentials.password == BASIC_AUTH_PASS:
        return True
    raise HTTPException(
        status_code=401,
        detail="Unauthorized access",
        headers={"WWW-Authenticate": "Basic"},
    )

class ExecutionState:
    def __init__(self):
        self.status: str = "Idle"
        self.current_prompt: str = ""
        self.progress_current: int = 0
        self.progress_total: int = 0
        self.cancel_requested: bool = False
        self.worker_thread: Optional[threading.Thread] = None
        self.log_history: deque = deque(maxlen=500)
        self.active_websockets: List[WebSocket] = []
        self.loop: Optional[asyncio.AbstractEventLoop] = None

state = ExecutionState()

def broadcast_log(message: str):
    timestamped = message
    state.log_history.append(timestamped)
    print(timestamped, flush=True)
    if state.loop and state.active_websockets:
        asyncio.run_coroutine_threadsafe(_send_ws_log(timestamped), state.loop)

async def _send_ws_log(message: str):
    disconnected = []
    for ws in state.active_websockets:
        try:
            await ws.send_json({"type": "log", "message": message, "status": state.status, "prompt": state.current_prompt})
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        if ws in state.active_websockets:
            state.active_websockets.remove(ws)

def is_cancel_requested() -> bool:
    return state.cancel_requested

def run_worker_task(single_index: Optional[int] = None):
    try:
        state.status = "Running"
        state.cancel_requested = False
        broadcast_log("[SYSTEM] Background automation task started.")
        engine.run_pipeline_sync(
            log_callback=broadcast_log,
            cancel_check=is_cancel_requested,
            single_row_index=single_index
        )
    except Exception as e:
        broadcast_log(f"[SYSTEM ERROR] Pipeline crashed: {e}")
    finally:
        state.status = "Idle"
        state.current_prompt = ""
        state.cancel_requested = False
        broadcast_log("[SYSTEM] Task finished. Status set to Idle.")

def run_login_task():
    try:
        state.status = "Running"
        broadcast_log("[SYSTEM] Launching Ideogram interactive login in Chrome...")
        engine.login_and_save_session()
        broadcast_log("[SYSTEM] Login Chrome session ready.")
    except Exception as e:
        broadcast_log(f"[SYSTEM ERROR] Login launch error: {e}")
    finally:
        state.status = "Idle"

class PromptAddRequest(BaseModel):
    prompt: str

class PromptUpdateRequest(BaseModel):
    id: int
    prompt: Optional[str] = None
    status: Optional[str] = None

class PromptDeleteRequest(BaseModel):
    id: int

class SingleRunRequest(BaseModel):
    id: int

class SettingsUpdateRequest(BaseModel):
    REPLICATE_API_TOKEN: Optional[str] = None
    SCORE_THRESHOLD: Optional[int] = None
    MAX_RETRIES: Optional[int] = None
    CLIPROXY_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None

@app.on_event("startup")
async def startup_event():
    state.loop = asyncio.get_running_loop()

@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request, authenticated: bool = Depends(check_auth)):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "vnc_port": 6080
    })

@app.get("/api/status")
async def get_status(authenticated: bool = Depends(check_auth)):
    prompts = engine.read_prompts_csv()
    done_count = sum(1 for p in prompts if p["status"] == "Done")
    failed_count = sum(1 for p in prompts if p["status"] == "Failed")
    pending_count = sum(1 for p in prompts if not p["status"])
    images = list(OUTPUT_DIR.glob("*.jpg")) + list(OUTPUT_DIR.glob("*.png"))
    return {
        "status": state.status,
        "current_prompt": state.current_prompt,
        "total_prompts": len(prompts),
        "done_count": done_count,
        "failed_count": failed_count,
        "pending_count": pending_count,
        "image_count": len(images)
    }

@app.get("/api/settings")
async def get_settings(authenticated: bool = Depends(check_auth)):
    return engine.load_settings()

@app.post("/api/settings")
async def update_settings(req: SettingsUpdateRequest, authenticated: bool = Depends(check_auth)):
    updates = req.dict(exclude_unset=True)
    saved = engine.save_settings(updates)
    broadcast_log("[SYSTEM] Application settings updated.")
    return {"success": True, "settings": saved}

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

@app.post("/api/prompts/reset-failed")
async def reset_failed_prompts(authenticated: bool = Depends(check_auth)):
    reset_count = engine.reset_failed_prompts()
    broadcast_log(f"[SYSTEM] Reset {reset_count} failed prompt(s) back to pending.")
    return {"success": True, "reset_count": reset_count, "prompts": engine.read_prompts_csv()}

@app.post("/api/run")
async def trigger_run(authenticated: bool = Depends(check_auth)):
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
    for file in sorted(OUTPUT_DIR.glob("*.*"), key=os.path.getmtime, reverse=True):
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

@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await websocket.accept()
    state.active_websockets.append(websocket)
    try:
        await websocket.send_json({
            "type": "history",
            "logs": list(state.log_history),
            "status": state.status,
            "prompt": state.current_prompt
        })
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in state.active_websockets:
            state.active_websockets.remove(websocket)
    except Exception:
        if websocket in state.active_websockets:
            state.active_websockets.remove(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
