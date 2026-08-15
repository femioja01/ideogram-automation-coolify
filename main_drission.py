"""
Pinterest Image Automation (DrissionPage Version)
-------------------------------------------------
Bypasses Cloudflare anti-bot checks by using DrissionPage (which communicates via
direct CDP connection, hiding standard Webdriver/Automation signatures).
"""

import os
import csv
import json
import base64
import shutil
import requests
import re
import sys
import asyncio
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Import DrissionPage elements
from DrissionPage import ChromiumPage, ChromiumOptions

load_dotenv()

# ── Config & Settings ─────────────────────────────────────────────────────────

PROMPTS_DIR   = Path("prompts_data")
PROMPTS_DIR.mkdir(exist_ok=True)

CSV_FILE      = PROMPTS_DIR / "prompts.csv"
SETTINGS_FILE = PROMPTS_DIR / "settings.json"

# Migration check: if root files exist but not in prompts_data, copy them over
if Path("prompts.csv").exists() and not CSV_FILE.exists():
    try:
        shutil.copy2("prompts.csv", CSV_FILE)
    except Exception:
        pass

if Path("settings.json").exists() and not SETTINGS_FILE.exists():
    try:
        shutil.copy2("settings.json", SETTINGS_FILE)
    except Exception:
        pass

output_env = os.getenv("OUTPUT_DIR", "").strip()
OUTPUT_DIR    = Path(output_env if output_env else "output_images")
PROFILE_DIR   = Path("chrome_profile")
TEMP_DIR      = Path("temp_downloads")

OUTPUT_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)

def load_settings() -> dict:
    """Load settings from settings.json falling back to environment variables."""
    defaults = {
        "REPLICATE_API_TOKEN": os.getenv("REPLICATE_API_TOKEN", "").strip(),
        "SCORE_THRESHOLD": 6,
        "MAX_RETRIES": 2,
        "CLIPROXY_API_KEY": os.getenv("CLIPROXY_API_KEY", "").strip(),
        "CLIPROXY_BASE_URL": os.getenv("CLIPROXY_BASE_URL", "https://cli-proxy-api.femioja.cfd").rstrip('/'),
        "CLIPROXY_MODEL": os.getenv("CLIPROXY_MODEL", "gemini-3.5-flash-low").strip(),
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", "").strip()
    }
    if SETTINGS_FILE.exists():
        try:
            stored = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            for k, v in stored.items():
                if v is not None:
                    defaults[k] = v
        except Exception as e:
            print(f"Warning reading settings.json: {e}")
    return defaults

def save_settings(new_settings: dict) -> dict:
    """Save updated settings dictionary to settings.json."""
    current = load_settings()
    for k, v in new_settings.items():
        if k in ["SCORE_THRESHOLD", "MAX_RETRIES"]:
            try:
                current[k] = int(v)
            except (ValueError, TypeError):
                pass
        else:
            current[k] = str(v).strip()
    
    try:
        SETTINGS_FILE.write_text(json.dumps(current, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"Error saving settings.json: {e}")
    return current

# ── CSV Helpers ───────────────────────────────────────────────────────────────

def ensure_csv_file():
    """Ensure prompts.csv exists with header."""
    if not CSV_FILE.exists():
        CSV_FILE.write_text("prompt,status,filename,date,score,image_url\n", encoding="utf-8")

def read_prompts_csv():
    """Return all rows from CSV as a list of dicts with 1-based index."""
    ensure_csv_file()
    with open(CSV_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or ["prompt","status","filename","date","score","image_url"]
        rows = list(reader)
    
    result = []
    for idx, row in enumerate(rows):
        result.append({
            "id": idx,
            "prompt": row.get("prompt", "").strip(),
            "status": row.get("status", "").strip(),
            "filename": row.get("filename", "").strip(),
            "date": row.get("date", "").strip(),
            "score": row.get("score", "").strip(),
            "image_url": row.get("image_url", "").strip(),
        })
    return result

def add_prompt_csv(prompt: str) -> bool:
    """Add a new prompt row to CSV."""
    ensure_csv_file()
    rows = read_prompts_csv()
    rows.append({
        "prompt": prompt.strip(),
        "status": "",
        "filename": "",
        "date": "",
        "score": "",
        "image_url": ""
    })
    return save_prompts_csv(rows)

def update_prompt_csv(row_index: int, prompt: str = None, status: str = None) -> bool:
    """Update a specific row in the CSV."""
    rows = read_prompts_csv()
    if 0 <= row_index < len(rows):
        if prompt is not None:
            rows[row_index]["prompt"] = prompt.strip()
        if status is not None:
            rows[row_index]["status"] = status.strip()
        return save_prompts_csv(rows)
    return False

def delete_prompt_csv(row_index: int) -> bool:
    """Delete a prompt row from CSV."""
    rows = read_prompts_csv()
    if 0 <= row_index < len(rows):
        rows.pop(row_index)
        return save_prompts_csv(rows)
    return False

def delete_multiple_prompts_csv(row_indices: list[int]) -> int:
    """Delete multiple prompt rows from CSV by index list."""
    rows = read_prompts_csv()
    indices_set = set(row_indices)
    new_rows = [r for idx, r in enumerate(rows) if idx not in indices_set]
    deleted_count = len(rows) - len(new_rows)
    if deleted_count > 0:
        save_prompts_csv(new_rows)
    return deleted_count

def clear_all_prompts_csv() -> bool:
    """Clear all prompt rows from CSV."""
    return save_prompts_csv([])

def reset_failed_prompts() -> int:
    """Reset status of all Failed prompts to blank."""
    rows = read_prompts_csv()
    count = 0
    for r in rows:
        if r["status"] == "Failed":
            r["status"] = ""
            count += 1
    if count > 0:
        save_prompts_csv(rows)
    return count

def save_prompts_csv(rows: list) -> bool:
    """Save list of prompt dicts back to CSV file."""
    fieldnames = ["prompt", "status", "filename", "date", "score", "image_url"]
    try:
        with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in rows:
                writer.writerow({
                    "prompt": r.get("prompt", ""),
                    "status": r.get("status", ""),
                    "filename": r.get("filename", ""),
                    "date": r.get("date", ""),
                    "score": r.get("score", ""),
                    "image_url": r.get("image_url", "")
                })
        return True
    except Exception as e:
        print(f"Error saving CSV: {e}")
        return False

def get_next_prompt():
    """Return (row_index, prompt) for the first row with blank status."""
    rows = read_prompts_csv()
    for i, row in enumerate(rows):
        prompt = row.get("prompt", "").strip()
        status = row.get("status", "").strip()
        if prompt and not status:
            return i, prompt
    return None, None

def update_csv_row(row_index: int, status: str, filename: str = "", score: str = "", image_url: str = ""):
    """Update a specific row in the CSV with results."""
    ensure_csv_file()
    rows = read_prompts_csv()
    if 0 <= row_index < len(rows):
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        rows[row_index]["status"]    = status
        rows[row_index]["filename"]  = filename
        rows[row_index]["date"]      = now
        rows[row_index]["score"]     = score
        rows[row_index]["image_url"] = image_url
        save_prompts_csv(rows)

# ── DrissionPage Helpers ───────────────────────────────────────────────────────

def get_browser_options(headless=False):
    """Setup Chromium options for DrissionPage stealth profile."""
    co = ChromiumOptions()
    co.set_user_data_path(str(PROFILE_DIR.resolve()))
    co.set_argument("--no-sandbox")
    co.set_argument("--disable-gpu")
    co.set_argument("--disable-dev-shm-usage")
    co.set_argument("--disable-blink-features=AutomationControlled")
    if headless:
        co.set_argument("--headless=new")
    return co

def login_and_save_session(log_fn=print):
    """Run interactively in browser window to save Ideogram login state."""
    co = get_browser_options(headless=False)
    page = ChromiumPage(co)
    try:
        log_fn("\nOpening Ideogram Login Page...")
        page.get("https://ideogram.ai/login")
        log_fn("\n=== ACTION REQUIRED ===")
        log_fn("Chrome window is now open.")
        log_fn("Please sign into Ideogram using Google Sign-In or your preferred method.")
        log_fn("The browser window will stay open unconditionally for 5 minutes (300 seconds).")
        
        # Keep open unconditionally for 300 seconds (5 minutes) so Google OAuth popups work seamlessly
        for _ in range(300):
            page.wait(1)
        log_fn("\n✓ Login window session time ended. Chrome profile saved!")
    except Exception as e:
        log_fn(f"Login window note: {e}")
    finally:
        try:
            page.quit()
        except Exception:
            pass

def generate_images_on_ideogram(prompt: str, excluded_urls: set[str] = None, log_fn=print) -> list[str]:
    """
    Opens Ideogram in Chrome, submits prompt,
    waits for generation, returns list of 4 image URLs.
    """
    if not PROFILE_DIR.exists():
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    co = get_browser_options(headless=False)
    page = ChromiumPage(co)
    
    try:
        log_fn("  Checking latest image in library to avoid downloading old images...")
        page.get("https://ideogram.ai/library/my-images")
        
        last_known_image = None
        for _ in range(5):
            page.wait(2)
            img_ele = page.ele('css:img[src*="ideogram.ai/assets/image"]')
            if img_ele:
                last_known_image = img_ele.attr('src')
                break
        
        log_fn(f"  Last known image: {last_known_image}")

        log_fn("  Navigating to Ideogram home to generate...")
        page.get("https://ideogram.ai/")
        page.wait(3)

        log_fn("  Injecting typing and generation script...")
        js_code = """
        const promptText = arguments[0];
        function isInsideSecondaryArea(element) {
            const selector = '[class*="card"], [class*="result"], [class*="sidebar"], [class*="modal"], [role="dialog"]';
            return !!element.closest(selector);
        }
        function findPromptInput() {
            const selectors = ['div.tiptap-prompt-editor', 'div.ProseMirror', '[contenteditable="true"]', 'textarea', 'input[type="text"]'];
            const elements = [];
            for (const selector of selectors) document.querySelectorAll(selector).forEach(el => elements.push(el));
            const visibleElements = elements.filter(el => el.offsetParent !== null);
            if (visibleElements.length === 0) return null;
            return visibleElements.find(el => !isInsideSecondaryArea(el)) || visibleElements[0];
        }
        function isAttachmentButton(button) {
            const ariaLabel = button.getAttribute('aria-label')?.toLowerCase() || '';
            const title = button.getAttribute('title')?.toLowerCase() || '';
            const className = button.className?.toLowerCase() || '';
            if (ariaLabel.includes('attach') || ariaLabel.includes('upload') || ariaLabel.includes('file') ||
                title.includes('attach') || title.includes('upload') || title.includes('file') ||
                className.includes('attach') || className.includes('upload')) return true;
            const svg = button.querySelector('svg');
            if (svg) {
                const svgClass = svg.getAttribute('class')?.toLowerCase() || '';
                const svgAriaLabel = svg.getAttribute('aria-label')?.toLowerCase() || '';
                if (svgClass.includes('paperclip') || svgClass.includes('attach') || 
                    svgAriaLabel.includes('attach') || svgAriaLabel.includes('paperclip')) return true;
            }
            return false;
        }
        function findGenerateButton(textarea) {
            if (!textarea) return null;
            let container = textarea.closest('div[class*="input"]') || textarea.closest('div[class*="prompt"]') || textarea.closest('form') || textarea.parentElement;
            let searchDepth = 0;
            while (container && searchDepth < 5) {
                const buttons = container.querySelectorAll('button');
                if (buttons.length > 0) {
                    const validButtons = Array.from(buttons).filter(button => 
                        button.offsetParent !== null && !button.disabled && !isInsideSecondaryArea(button) && !isAttachmentButton(button)
                    );
                    if (validButtons.length > 0) {
                        for (const button of validButtons) {
                            const type = button.getAttribute('type');
                            const ariaLabel = button.getAttribute('aria-label')?.toLowerCase() || '';
                            const title = button.getAttribute('title')?.toLowerCase() || '';
                            const text = button.textContent.toLowerCase().trim();
                            if (type === 'submit' || ariaLabel.includes('generate') || ariaLabel.includes('create') ||
                                ariaLabel.includes('submit') || text === 'generate') return button;
                        }
                        return validButtons[validButtons.length - 1]; 
                    }
                }
                container = container.parentElement;
                searchDepth++;
            }
            return null;
        }

        return new Promise((resolve) => {
            const input = findPromptInput();
            if (!input) { resolve("no_input"); return; }
            
            input.focus();
            if (input.isContentEditable) {
                try {
                    const selection = window.getSelection();
                    const range = document.createRange();
                    range.selectNodeContents(input);
                    selection.removeAllRanges();
                    selection.addRange(range);
                    if (!document.execCommand('insertText', false, promptText)) input.innerHTML = promptText;
                } catch (e) {
                    input.innerHTML = promptText;
                }
                input.dispatchEvent(new InputEvent('input', { bubbles: true, cancelable: true }));
            } else {
                input.value = promptText;
                input.dispatchEvent(new Event('input', { bubbles: true }));
            }
            
            setTimeout(() => {
                const btn = findGenerateButton(input);
                if (btn) {
                    btn.focus();
                    setTimeout(() => {
                        btn.click();
                        resolve("success");
                    }, 500);
                } else {
                    resolve("no_button");
                }
            }, 500);
        });
        """
        
        inj_result = page.run_js(js_code, prompt)
        log_fn(f"  Injection result: {inj_result}")
        page.wait(3)

        log_fn("  Generation submitted. Navigating to My Images to await results...")
        page.get("https://ideogram.ai/library/my-images")

        image_urls = []
        for _ in range(40): # Wait up to 120 seconds
            page.wait(3)
            imgs = page.run_js("""
                const imgs = Array.from(document.querySelectorAll('img[src*="ideogram.ai/assets/image"]'));
                return imgs.slice(0, 4).map(img => img.src);
            """)
            
            is_new = False
            if imgs and len(imgs) >= 4:
                is_new = (imgs[0] != last_known_image)
                if excluded_urls:
                    is_new = is_new and (imgs[0] not in excluded_urls)

            if is_new:
                log_fn(f"  Detected {len(imgs)} new images!")
                image_urls = imgs
                break

        if not image_urls:
            raise RuntimeError("Could not find generated images on Ideogram page.")

        return image_urls

    finally:
        page.quit()

# ── Vision Scoring ───────────────────────────────────────────────────────────

def download_image(url: str, path: Path):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    path.write_bytes(r.content)

def score_image(image_path: Path, prompt: str, image_url: str = None, log_fn=print) -> dict:
    """Scores visual assets using Vision models configured in settings."""
    cfg = load_settings()
    
    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")
    base64_url = f"data:image/jpeg;base64,{image_data}"
    
    scoring_prompt = (
        f'USER: Look closely at this image.\n'
        f'The user requested this text: "{prompt}".\n'
        f'1. Read all the text in the image. Are there any misspelled words (like "Fhorth", "Craass", "ACTIVIT")? If yes, point them out.\n'
        f'2. Look at any people in the image. Check for anatomical errors: Do they have exactly 5 normal fingers and 5 normal toes? Are faces distorted or melted? Are there extra or missing limbs?\n'
        f'3. Calculate a score from 1 to 10. Deduct 5 points for ANY misspelled text and 5 points for ANY anatomical distortions (melted faces, weird fingers/toes, extra limbs).\n\n'
        f'Provide your explanation, and then at the very end write exactly: "FINAL_SCORE: X" (where X is your final number from 1 to 10).\n'
        f'ASSISTANT:'
    )

    cliproxy_key = cfg.get("CLIPROXY_API_KEY")
    cliproxy_base_url = cfg.get("CLIPROXY_BASE_URL", "https://cli-proxy-api.femioja.cfd").rstrip('/')
    cliproxy_model = cfg.get("CLIPROXY_MODEL", "gemini-3.5-flash-low")

    if cliproxy_key:
        log_fn(f"  Scoring image using CLIProxy model: {cliproxy_model}...")
        payload = {
            "model": cliproxy_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": scoring_prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}}
                    ]
                }
            ],
            "max_tokens": 800,
            "temperature": 0.1
        }
        headers = {
            "Authorization": f"Bearer {cliproxy_key}",
            "Content-Type": "application/json"
        }
        try:
            resp = requests.post(f"{cliproxy_base_url}/v1/chat/completions", headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            resp_json = resp.json()
            if "choices" in resp_json and len(resp_json["choices"]) > 0:
                raw = resp_json["choices"][0]["message"]["content"].strip()
            else:
                raw = f"Error: Invalid structure in CLIProxy response: {resp_json}"
        except Exception as e:
            raw = f"Error querying CLIProxy: {e}"
    else:
        openai_key = cfg.get("OPENAI_API_KEY")
        if openai_key:
            log_fn("  Scoring image using OpenAI GPT-4o-Mini...")
            payload = {
                "model": "gpt-4o-mini",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": scoring_prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}}
                        ]
                    }
                ],
                "max_tokens": 800,
                "temperature": 0.1
            }
            resp = requests.post("https://api.openai.com/v1/chat/completions", headers={"Authorization": f"Bearer {openai_key}"}, json=payload)
            resp_json = resp.json()
            if "choices" in resp_json:
                raw = resp_json["choices"][0]["message"]["content"].strip()
            else:
                raw = f"Error: {resp_json}"
        else:
            rep_token = cfg.get("REPLICATE_API_TOKEN")
            if not rep_token:
                log_fn("  Warning: No Vision API key (REPLICATE_API_TOKEN) configured. Defaulting score to 7.")
                return {"score": 7, "reason": "No Vision API key configured in app settings or environment."}
            
            log_fn("  Scoring image using Replicate GPT-4o-Mini...")
            os.environ["REPLICATE_API_TOKEN"] = rep_token
            remote_img = image_url if image_url else base64_url

            try:
                import replicate
                output = replicate.run(
                    "openai/gpt-4o-mini",
                    input={
                        "prompt": scoring_prompt,
                        "image_input": [remote_img] if remote_img.startswith("http") else [open(image_path, "rb")],
                        "max_completion_tokens": 800,
                        "temperature": 0.1
                    }
                )
                raw = "".join(output).strip()
            except Exception as e:
                raw = f"Error querying Replicate: {e}"

    match = re.search(r'FINAL_SCORE:\s*([0-9]+)', raw, re.IGNORECASE)
    score = 0
    if match:
        try:
            score = int(match.group(1))
        except ValueError:
            score = 0

    return {
        "score": score,
        "issues": [raw[:200] + "..."],
        "reason": raw
    }

# ── Main Pipeline ─────────────────────────────────────────────────────────────

def run_pipeline_sync(log_callback=None, cancel_check=None, single_row_index=None):
    """Synchronous execution of prompt batch with dynamic settings."""
    cfg = load_settings()
    score_threshold = cfg.get("SCORE_THRESHOLD", 6)
    max_retries = cfg.get("MAX_RETRIES", 2)

    def log(msg):
        print(msg, flush=True)
        if log_callback:
            try:
                log_callback(msg)
            except Exception:
                pass

    log(f"\n{'='*50}")
    log(f"Pinterest Automation Engine — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    log(f"Config: Score Threshold={score_threshold}, Max Retries={max_retries}")
    log(f"{'='*50}")

    ensure_csv_file()
    all_rows = read_prompts_csv()

    if single_row_index is not None:
        if 0 <= single_row_index < len(all_rows):
            pending_tasks = [(single_row_index, all_rows[single_row_index]["prompt"])]
        else:
            log(f"Error: Invalid prompt row index {single_row_index}")
            return
    else:
        pending_tasks = []
        for i, row in enumerate(all_rows):
            prompt = row.get("prompt", "").strip()
            status = row.get("status", "").strip()
            if prompt and not status:
                pending_tasks.append((i, prompt))

    if not pending_tasks:
        log("\nNo pending prompts found in prompts.csv. All done!")
        return

    log(f"Found {len(pending_tasks)} pending prompt(s). Starting execution...")
    processed_urls = set()

    for task_idx, (row_index, prompt) in enumerate(pending_tasks, 1):
        if cancel_check and cancel_check():
            log("\n[STOPPED] Execution cancelled by user command.")
            break

        log(f"\n{'─'*50}")
        log(f"[{task_idx}/{len(pending_tasks)}] Processing Row {row_index + 1} | Prompt: {prompt[:80]}...")
        
        best_image_path = None
        best_image_url  = ""
        best_score      = 0

        for attempt in range(1, max_retries + 1):
            if cancel_check and cancel_check():
                log("  Execution cancelled during retries.")
                break

            log(f"\nAttempt {attempt}/{max_retries} — Generating images on Ideogram...")

            try:
                image_urls = generate_images_on_ideogram(prompt, excluded_urls=processed_urls, log_fn=log)
            except Exception as e:
                log(f"  ERROR generating images: {e}")
                continue

            log(f"  Got {len(image_urls)} image URLs. Scoring with Vision LLM...")
            processed_urls.update(image_urls)

            attempt_best_path  = None
            attempt_best_url   = ""
            attempt_best_score = 0

            for idx, url in enumerate(image_urls, 1):
                local_path = TEMP_DIR / f"attempt{attempt}_img{idx}.jpg"
                try:
                    download_image(url, local_path)
                    result = score_image(local_path, prompt, image_url=url, log_fn=log)
                    score  = result.get("score", 0)
                    log(f"  Image {idx}: score={score}")

                    if score > attempt_best_score:
                        attempt_best_score = score
                        attempt_best_path  = local_path
                        attempt_best_url   = url

                except Exception as e:
                    log(f"  Image {idx}: ERROR — {e}")

            if attempt_best_score >= score_threshold:
                best_score      = attempt_best_score
                best_image_path = attempt_best_path
                best_image_url  = attempt_best_url
                log(f"\n  ✓ Acceptable image found (score {best_score}/10)")
                break
            else:
                log(f"\n  All images scored below threshold {score_threshold}. Retrying...")

        if best_image_path and best_score >= score_threshold:
            safe_prompt = re.sub(r'[^a-zA-Z0-9]', '_', prompt[:40])
            safe_prompt = re.sub(r'_+', '_', safe_prompt).strip('_')
            filename    = f"{datetime.now().strftime('%Y%m%d')}_{safe_prompt}.jpg"
            final_path  = OUTPUT_DIR / filename

            shutil.copy2(best_image_path, final_path)
            update_csv_row(row_index, "Done", filename, str(best_score), best_image_url)
            log(f"\n✓ Done! Image saved to: {final_path.resolve()}")
        else:
            log(f"\n✗ All attempts failed for this prompt. Marking row as Failed.")
            update_csv_row(row_index, "Failed", "", str(best_score), best_image_url)

        # Clean up temp images
        for f in TEMP_DIR.glob("attempt*_img*.jpg"):
            f.unlink(missing_ok=True)

    log("\nPipeline run complete.")

if __name__ == "__main__":
    if "--login" in sys.argv:
        login_and_save_session()
    else:
        run_pipeline_sync()
