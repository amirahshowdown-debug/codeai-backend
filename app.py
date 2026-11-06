
"""
Programming-only AI Backend (Gemini)
Modes: Generate Code, Explain, Fix Bug
Code execution and sandbox are disabled.
"""

import os
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

BASE_PROMPT = """
You are a professional programming-only AI assistant.

Rules:
- Only answer programming, software development,
  debugging and computer science questions.
- For non-programming questions, politely refuse.
- When providing code, return the complete code.
- Never claim that code was executed or tested.
- Explain errors and solutions clearly.
- Keep explanations simple and practical.
"""

LANG_RULES = {
    "auto": "Reply in the same language the user writes in.",
    "bangla": "Reply in Bengali using Bangla script.",
    "banglish": "Reply in Bengali written with English letters.",
    "english": "Reply in English.",
}


class Answer(BaseModel):
    is_programming: bool
    explanation: str
    language: str = ""
    code: str = ""


class ChatIn(BaseModel):
    session_id: str
    message: str
    mode: str = "code"
    reply_language: str = "auto"


class ResetIn(BaseModel):
    session_id: str


app = FastAPI(
    title="Code AI Backend",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SESSIONS: Dict[str, List[types.Content]] = {}


def to_content(role: str, text: str) -> types.Content:
    return types.Content(
        role=role,
        parts=[types.Part.from_text(text=text)]
    )


def ask_gemini(
    client,
    model: str,
    system: str,
    contents: List[types.Content]
) -> Answer:

    resp = client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=Answer,
            temperature=0.2,
        ),
    )

    if resp.parsed is not None:
        return resp.parsed

    try:
        return Answer.model_validate_json(resp.text)
    except Exception:
        return Answer(
            is_programming=True,
            explanation=resp.text or "Please try again.",
        )


@app.get("/")
def index():
    return {
        "name": "Code AI Backend",
        "status": "running",
        "execution": "disabled",
        "modes": ["code", "explain", "debug"],
    }


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "Code AI Backend",
        "execution": False,
    }


@app.post("/reset")
def reset(body: ResetIn):
    SESSIONS.pop(body.session_id, None)
    return {"ok": True}


@app.post("/chat")
def chat(body: ChatIn):

    if not ENV_KEY or ENV_KEY == "PASTE_YOUR_GEMINI_API_KEY_HERE":
        raise HTTPException(
            status_code=500,
            detail="Server GEMINI_API_KEY is not configured."
        )

    mode = body.mode.lower().strip()

    if mode not in {"code", "explain", "debug"}:
        mode = "code"

    reply_language = body.reply_language.lower().strip()

    if reply_language not in LANG_RULES:
        reply_language = "auto"

    mode_prompts = {
        "code": """
MODE: Generate complete, practical code.
Explain the code briefly.
""",
        "explain": """
MODE: Explain the supplied code or programming concept
step by step. Avoid unnecessary code generation.
""",
        "debug": """
MODE: Find bugs in the supplied code.
Explain the errors and provide the complete corrected code.
""",
    }

    system = (
        BASE_PROMPT
        + mode_prompts[mode]
        + "\n"
        + LANG_RULES[reply_language]
    )

    client = genai.Client(api_key=ENV_KEY)

    history = SESSIONS.setdefault(body.session_id, [])

    history.append(to_content("user", body.message))

    try:
        answer = ask_gemini(
            client,
            DEFAULT_MODEL,
            system,
            list(history),
        )

        if not answer.is_programming:
            history.append(
                to_content("model", answer.explanation)
            )

            return {
                "reply": answer.explanation,
                "code": "",
                "language": "",
                "mode": mode,
                "execution": False,
            }

        history.append(
            to_content(
                "model",
                answer.explanation + "\n" + answer.code
            )
        )

        # Keep recent conversation history limited.
        if len(history) > 30:
            SESSIONS[body.session_id] = history[-30:]

        return {
            "reply": answer.explanation,
            "code": answer.code,
            "language": answer.language,
            "mode": mode,
            "execution": False,
        }

    except Exception as e:
        if history:
            history.pop()

        raise HTTPException(
            status_code=502,
            detail=f"Gemini error: {str(e)}"
        )
