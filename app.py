"""
Programming-only AI (Gemini) with Generate Code, Explain, and Fix Bug modes.

Flow:
  user message -> Gemini (JSON answer) -> run code in sandbox
     -> OK    : send to user
     -> ERROR : send error back to Gemini, ask to fix (max N attempts) -> send fixed code

Run:
  pip install -r requirements.txt
  copy .env.example .env   # .env file e GEMINI_API_KEY boshao
  uvicorn app:app --reload
"""
import os
import shutil
import subprocess
import tempfile
from typing import Dict, List

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types
from pydantic import BaseModel

load_dotenv()
ENV_KEY = os.getenv("GEMINI_API_KEY", "")
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
USE_DOCKER = os.getenv("USE_DOCKER", "0") == "1"  # production e docker use koro

BASE_PROMPT = """You are a programming-only assistant.
- Only answer programming / software development / debugging / computer-science questions.
- If the question is NOT about programming, set is_programming=false and politely refuse in 'explanation'.
- When you give code, put the COMPLETE runnable code in 'code' and set 'language' to
  'python' or 'javascript' when possible. Code must be self-contained, no user input() / no network,
  and should print visible output or include simple asserts/tests so that success can be verified.
- If code cannot be run standalone (HTML/CSS, snippets, config), set runnable=false.
- Keep 'explanation' short and clear."""

LANG_RULES = {
    "auto": "Reply in the same language the user writes in.",
    "bangla": "Reply in Bengali (Bangla script).",
    "banglish": "Reply in Bengali written with English letters (Banglish).",
    "english": "Reply in English.",
}


class Answer(BaseModel):
    is_programming: bool
    explanation: str
    language: str = ""
    code: str = ""
    runnable: bool = False


class ChatIn(BaseModel):
    session_id: str
    message: str
    mode: str = "code"


# ---------------- Sandbox runner ----------------
RUNNERS = {
    "python": ("main.py", ["python3", "main.py"], "python:3.12-slim"),
    "javascript": ("main.js", ["node", "main.js"], "node:20-slim"),
}


def run_code(language: str, code: str, timeout: int):
    """Returns (ok: bool|None, output: str). None = run kora support kore na."""
    lang = language.lower().strip()
    if lang in ("py",):
        lang = "python"
    if lang in ("js", "node", "nodejs"):
        lang = "javascript"
    if lang not in RUNNERS:
        return None, f"'{language}' run kora support kore na"

    filename, cmd, image = RUNNERS[lang]
    tmp = tempfile.mkdtemp(prefix="sandbox_")
    try:
        with open(os.path.join(tmp, filename), "w", encoding="utf-8") as f:
            f.write(code)

        if USE_DOCKER:
            full_cmd = [
                "docker", "run", "--rm", "--network", "none",
                "--memory", "256m", "--cpus", "1", "--pids-limit", "64",
                "-v", f"{tmp}:/app:ro", "-w", "/app", image, *cmd,
            ]
        else:
            full_cmd = cmd  # WARNING: not isolated, only for local testing

        p = subprocess.run(full_cmd, cwd=tmp, capture_output=True, text=True, timeout=timeout)
        out = (p.stdout + ("\n" + p.stderr if p.stderr else "")).strip()
        return p.returncode == 0, out[:3000]
    except subprocess.TimeoutExpired:
        return False, f"Timeout: code {timeout}s er moddhe shesh hoy nai"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------- Gemini ----------------
def ask_gemini(client, model: str, temperature: float, system: str,
               contents: List[types.Content]) -> Answer:
    resp = client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=Answer,
            temperature=temperature,
        ),
    )
    if resp.parsed is not None:
        return resp.parsed
    try:
        return Answer.model_validate_json(resp.text)
    except Exception:
        return Answer(is_programming=True,
                      explanation=resp.text or "Kichu ekta problem hoyeche, abar try koro.")


def to_content(role: str, text: str) -> types.Content:
    return types.Content(role=role, parts=[types.Part.from_text(text=text)])


# ---------------- API ----------------
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
SESSIONS: Dict[str, List[types.Content]] = {}


@app.get("/")
def index():
    return {
        "name": "Code AI Backend",
        "status": "running",
        "endpoints": ["/health", "/chat", "/reset"]
    }


@app.get("/health")
def health():
    return {"ok": True, "service": "Code AI Backend"}


@app.post("/reset")
def reset(body: ChatIn):
    SESSIONS.pop(body.session_id, None)
    return {"ok": True}


@app.post("/chat")
def chat(body: ChatIn):
    # API key stays on the server in .env; it is never sent by the browser.
    key = ENV_KEY
    if not key or key == "PASTE_YOUR_GEMINI_API_KEY_HERE":
        raise HTTPException(500, "Server-er .env file e valid GEMINI_API_KEY set kora nei.")

    model = DEFAULT_MODEL
    temperature = 0.2
    max_fix = 3
    timeout = 10
    mode = body.mode if body.mode in {"code", "explain", "debug"} else "code"
    mode_prompts = {
        "code": "\nMODE: Generate complete, practical code for the user's request. Explain briefly.",
        "explain": "\nMODE: Explain the programming concept or supplied code in simple steps. Do not generate code unless a tiny example is essential.",
        "debug": "\nMODE: Debug the code supplied by the user. Identify the issue and return the complete corrected code when possible.",
    }
    system = BASE_PROMPT + mode_prompts[mode] + "\n" + LANG_RULES["auto"]

    client = genai.Client(api_key=key)
    history = SESSIONS.setdefault(body.session_id, [])
    history.append(to_content("user", body.message))
    work = list(history)  # fix-loop er internal message gulo history te jabe na

    try:
        ans = ask_gemini(client, model, temperature, system, work)

        if not ans.is_programming:
            history.append(to_content("model", ans.explanation))
            return {"reply": ans.explanation, "code": "", "verified": False, "attempts": 0}

        verified, output, attempts, note = False, "", 0, ""
        can_run = bool(ans.code and ans.runnable)

        if can_run:
            # 1 bar run + max_fix bar fix-and-rerun
            for attempts in range(1, max_fix + 2):
                ok, output = run_code(ans.language, ans.code, timeout)
                if ok is None:
                    note = output
                    break
                if ok:
                    verified = True
                    break
                if attempts > max_fix:
                    note = "Auto-fix er por-o code pass kore nai, review kore nio."
                    break
                work.append(to_content("model", ans.model_dump_json()))
                work.append(to_content(
                    "user",
                    f"Your code failed when executed.\nError/Output:\n{output}\n"
                    "Fix the code and return the full corrected answer.",
                ))
                ans = ask_gemini(client, model, temperature, system, work)

        history.append(to_content("model", ans.explanation + "\n" + ans.code))
        return {
            "reply": ans.explanation,
            "language": ans.language,
            "code": ans.code,
            "verified": verified,
            "run_output": output if verified else "",
            "attempts": attempts,
            "note": "" if verified else note,
        }
    except HTTPException:
        raise
    except Exception as e:
        history.pop()  # fail hole user message ta history theke soriye dao
        raise HTTPException(502, f"Gemini error: {e}")
