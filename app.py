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

@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

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
    for ws in list(state.active_websockets):
        try:
            await ws.send_json({"type": "log", "message": message})
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        if ws in state.active_websockets:
            state.active_websockets.remove(ws)

class SettingsUpdateRequest(BaseModel):
    REPLICATE_API_TOKEN: Optional[str] = ""
    SCORE_THRESHOLD: Optional[int] = 6
    MAX_RETRIES: Optional[int] = 2
    CLIPROXY_API_KEY: Optional[str] = ""
    CLIPROXY_BASE_URL: Optional[str] = "https://cli-proxy-api.femioja.cfd"
    CLIPROXY_MODEL: Optional[str] = "gemini-3.5-flash-low"
    OPENAI_API_KEY: Optional[str] = ""

class PromptAddRequest(BaseModel):
    prompt: str

class PromptUpdateRequest(BaseModel):
    id: int
    prompt: Optional[str] = None
    status: Optional[str] = None

class PromptDeleteRequest(BaseModel):
    id: int

class PromptBulkDeleteRequest(BaseModel):
    ids: List[int]

class SingleRunRequest(BaseModel):
    id: int

@app.on_event("startup")
async def startup_event():
    state.loop = asyncio.get_running_loop()

@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request, authenticated: bool = Depends(check_auth)):
    response = templates.TemplateResponse("index.html", {"request": request})
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.get("/api/status")
async def get_status(authenticated: bool = Depends(check_auth)):
    rows = engine.read_prompts_csv()
    total = len(rows)
    done = sum(1 for r in rows if r["status"] == "Done")
    failed = sum(1 for r in rows if r["status"] == "Failed")
    pending = sum(1 for r in rows if not r["status"])
    
    image_files = list(engine.OUTPUT_DIR.glob("*.jpg")) + list(engine.OUTPUT_DIR.glob("*.png"))

    return {
        "status": state.status,
        "current_prompt": state.current_prompt,
        "total_prompts": total,
        "done_count": done,
        "failed_count": failed,
        "pending_count": pending,
        "image_count": len(image_files)
    }

@app.get("/api/settings")
async def get_settings(authenticated: bool = Depends(check_auth)):
    return engine.load_settings()

@app.post("/api/settings")
async def update_settings(payload: SettingsUpdateRequest, authenticated: bool = Depends(check_auth)):
    updated = engine.save_settings(payload.dict())
    broadcast_log(f"[SYSTEM] Settings updated: Threshold={updated.get('SCORE_THRESHOLD')}, MaxRetries={updated.get('MAX_RETRIES')}")
    return {"success": True, "settings": updated}

@app.get("/api/prompts")
async def get_prompts(authenticated: bool = Depends(check_auth)):
    return engine.read_prompts_csv()

@app.post("/api/prompts/add")
async def add_prompt(payload: PromptAddRequest, authenticated: bool = Depends(check_auth)):
    if not payload.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")
    ok = engine.add_prompt_csv(payload.prompt)
    if ok:
        broadcast_log(f"[SYSTEM] Prompt added: '{payload.prompt[:40]}...'")
        return {"success": True, "prompts": engine.read_prompts_csv()}
    raise HTTPException(status_code=500, detail="Could not save prompt to CSV")

@app.post("/api/prompts/update")
async def update_prompt(payload: PromptUpdateRequest, authenticated: bool = Depends(check_auth)):
    ok = engine.update_prompt_csv(payload.id, prompt=payload.prompt, status=payload.status)
    if ok:
        return {"success": True, "prompts": engine.read_prompts_csv()}
    raise HTTPException(status_code=404, detail="Prompt index out of range")

@app.post("/api/prompts/delete")
async def delete_prompt(payload: PromptDeleteRequest, authenticated: bool = Depends(check_auth)):
    ok = engine.delete_prompt_csv(payload.id)
    if ok:
        return {"success": True, "prompts": engine.read_prompts_csv()}
    raise HTTPException(status_code=404, detail="Prompt index out of range")

@app.post("/api/prompts/delete-bulk")
async def delete_bulk_prompts(payload: PromptBulkDeleteRequest, authenticated: bool = Depends(check_auth)):
    deleted_count = engine.delete_multiple_prompts_csv(payload.ids)
    broadcast_log(f"[SYSTEM] Bulk deleted {deleted_count} prompt(s) from database.")
    return {"success": True, "deleted_count": deleted_count, "prompts": engine.read_prompts_csv()}

@app.post("/api/prompts/clear-all")
async def clear_all_prompts(authenticated: bool = Depends(check_auth)):
    ok = engine.clear_all_prompts_csv()
    broadcast_log("[SYSTEM] Cleared all prompts from database.")
    return {"success": True, "prompts": []}

@app.post("/api/prompts/reset-failed")
async def reset_failed_prompts(authenticated: bool = Depends(check_auth)):
    reset_count = engine.reset_failed_prompts()
    broadcast_log(f"[SYSTEM] Reset {reset_count} failed prompt(s) back to pending.")
    return {"success": True, "reset_count": reset_count, "prompts": engine.read_prompts_csv()}

@app.post("/api/prompts/reset-all")
async def reset_all_prompts_pending(authenticated: bool = Depends(check_auth)):
    reset_count = engine.reset_all_prompts_pending()
    broadcast_log(f"[SYSTEM] Reset {reset_count} prompt(s) back to pending.")
    return {"reset_count": reset_count, "prompts": engine.read_prompts_csv()}

@app.post("/api/run")
async def trigger_run(authenticated: bool = Depends(check_auth)):
    if state.status == "Running":
        return {"status": "already_running", "message": "Automation is already running."}

    state.status = "Running"
    state.cancel_requested = False

    def worker():
        try:
            broadcast_log("[SYSTEM] Background automation task started.")
            engine.run_pipeline_sync(
                log_callback=broadcast_log,
                cancel_check=lambda: state.cancel_requested
            )
        except Exception as e:
            broadcast_log(f"[ERROR] Automation task error: {e}")
        finally:
            state.status = "Idle"
            broadcast_log("[SYSTEM] Task finished. Status set to Idle.")

    state.worker_thread = threading.Thread(target=worker, daemon=True)
    state.worker_thread.start()

    return {"status": "started", "message": "Batch automation started."}

@app.post("/api/run-single")
async def trigger_run_single(payload: SingleRunRequest, authenticated: bool = Depends(check_auth)):
    if state.status == "Running":
        return {"status": "already_running", "message": "Automation is already running."}

    state.status = "Running"
    state.cancel_requested = False

    def worker():
        try:
            broadcast_log(f"[SYSTEM] Starting single prompt run for row index {payload.id}...")
            engine.run_pipeline_sync(
                log_callback=broadcast_log,
                cancel_check=lambda: state.cancel_requested,
                single_row_index=payload.id
            )
        except Exception as e:
            broadcast_log(f"[ERROR] Single prompt task error: {e}")
        finally:
            state.status = "Idle"
            broadcast_log("[SYSTEM] Task finished. Status set to Idle.")

    state.worker_thread = threading.Thread(target=worker, daemon=True)
    state.worker_thread.start()

    return {"status": "started", "message": f"Single prompt run started for row {payload.id + 1}."}

@app.post("/api/stop")
async def trigger_stop(authenticated: bool = Depends(check_auth)):
    if state.status != "Running":
        return {"status": "not_running", "message": "Automation is not running."}

    state.cancel_requested = True
    state.status = "Stopping"
    broadcast_log("[SYSTEM] Cancellation requested by user...")
    return {"status": "stopping", "message": "Stop request sent to automation engine."}

@app.post("/api/login")
async def trigger_login(authenticated: bool = Depends(check_auth)):
    if state.status == "Running":
        return {"status": "busy", "message": "Cannot launch login window while automation is running."}

    state.status = "Running"
    def login_worker():
        try:
            broadcast_log("[SYSTEM] Opening Ideogram login window...")
            engine.login_and_save_session(log_fn=broadcast_log)
        except Exception as e:
            broadcast_log(f"[ERROR] Login window error: {e}")
        finally:
            state.status = "Idle"
            broadcast_log("[SYSTEM] Login session task completed.")

    t = threading.Thread(target=login_worker, daemon=True)
    t.start()
    return {"status": "started", "message": "Login window launched on Mac desktop."}

@app.get("/api/gallery")
async def get_gallery(authenticated: bool = Depends(check_auth)):
    output_files = list(engine.OUTPUT_DIR.glob("*.jpg")) + list(engine.OUTPUT_DIR.glob("*.png"))
    output_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

    rows = engine.read_prompts_csv()
    filename_map = {r["filename"]: r for r in rows if r.get("filename")}

    gallery = []
    for f in output_files:
        meta = filename_map.get(f.name, {})
        gallery.append({
            "filename": f.name,
            "url": f"/output_images/{f.name}",
            "prompt": meta.get("prompt", f.stem),
            "score": meta.get("score", "N/A"),
            "date": meta.get("date", ""),
            "size_kb": round(f.stat().st_size / 1024, 1)
        })

    return gallery

@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await websocket.accept()
    state.active_websockets.append(websocket)
    try:
        await websocket.send_json({
            "type": "history",
            "logs": list(state.log_history)
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
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
