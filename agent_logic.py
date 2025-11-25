# agent_logic.py
import json
import os
from datetime import datetime
from pathlib import Path
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

MODEL_NAME = "models/gemini-2.5-flash"

INBOX_PATH = Path("data/mock_inbox.json")
PROMPT_PATH = Path("data/prompts.json")
DRAFT_PATH = Path("data/drafts.json")

def load_inbox():
    if INBOX_PATH.exists():
        return json.loads(INBOX_PATH.read_text(encoding="utf-8"))
    return []

def load_prompts():
    if PROMPT_PATH.exists():
        return json.loads(PROMPT_PATH.read_text(encoding="utf-8"))
    return {}

def load_drafts():
    if DRAFT_PATH.exists():
        return json.loads(DRAFT_PATH.read_text(encoding="utf-8"))
    return []

def save_prompts(prompts):
    PROMPT_PATH.write_text(json.dumps(prompts, indent=2), encoding="utf-8")

def save_drafts(drafts):
    DRAFT_PATH.write_text(json.dumps(drafts, indent=2), encoding="utf-8")

def call_gemini(system_prompt, user_prompt):
    model = genai.GenerativeModel(MODEL_NAME)
    full_prompt = system_prompt + "\n\n" + user_prompt
    response = model.generate_content(full_prompt)
    return response.text

def process_email(email_dict, prompts):
    categorization_prompt = prompts.get("categorization_prompt", "")
    action_prompt = prompts.get("action_item_prompt", "")

    body = email_dict.get("body", {})
    content = body.get("text") if isinstance(body, dict) else str(body)

    cat_user_prompt = f"Email:\n{content}\n\nReturn category and reason in JSON."
    try:
        cat_raw = call_gemini(categorization_prompt, cat_user_prompt)
        cat_json = json.loads(cat_raw)
    except Exception:
        cat_json = {"category": "Unknown", "reason": "Gemini parsing error"}

    act_user_prompt = f"Email:\n{content}\n\nReturn JSON array: [{{'task':..., 'deadline':...}}]"
    try:
        act_raw = call_gemini(action_prompt, act_user_prompt)
        actions = json.loads(act_raw)
    except Exception:
        actions = []

    return {
        **email_dict,
        "category": cat_json.get("category", "Unknown"),
        "category_reason": cat_json.get("reason", ""),
        "action_items": actions,
    }

def summarize_email(email):
    body = email.get("body", {})
    content = body.get("text") if isinstance(body, dict) else str(body)
    summary_prompt = "Summarize the email in 3-5 lines clearly."
    return call_gemini(summary_prompt, content)

def draft_reply(email, prompts, tone="professional"):
    body = email.get("body", {})
    content = body.get("text") if isinstance(body, dict) else str(body)

    auto_reply_prompt = prompts.get("auto_reply_prompt", "")
    user_prompt = f"Tone: {tone}\n\nOriginal Email:\n{content}"

    try:
        raw = call_gemini(auto_reply_prompt, user_prompt)
        draft = json.loads(raw)
    except Exception:
        draft = {
            "subject": "Re: " + (email.get("subject") or ""),
            "body": "Thank you for your email.",
            "suggested_followups": []
        }

    return draft
