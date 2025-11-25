# gmail_to_agent.py
import json
import time
from gmail_client import (
    gmail_authenticate,
    list_message_ids,
    get_message,
    create_label_if_not_exists,
    add_label_to_message,
)
from agent_logic import process_email, load_prompts
from pathlib import Path
from typing import List, Dict, Any, Optional

DATA_DIR = Path("data")
RAW_PATH = DATA_DIR / "gmail_raw.json"

def _save_raw_messages(raw_msgs: List[Dict[str, Any]]):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        if RAW_PATH.exists():
            existing = json.loads(RAW_PATH.read_text(encoding="utf-8") or "[]")
        else:
            existing = []
        existing.extend(raw_msgs)
        RAW_PATH.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    except Exception:
        pass

def _simple_simulate_processing(email: Dict[str, Any]) -> Dict[str, Any]:
    body_text = ""
    if isinstance(email.get("body"), dict):
        body_text = (email["body"].get("text") or "").lower()
        subj = (email.get("subject") or "").lower()
    else:
        body_text = str(email.get("body") or "").lower()
        subj = (email.get("subject") or "").lower()

    if any(w in body_text or w in subj for w in ["unsubscribe", "newsletter", "subscribe", "weekly"]):
        category = "Newsletter"
        reason = "Contains newsletter/unsubscribe keywords"
    elif any(w in body_text or w in subj for w in ["free", "win", "congratulations", "offer"]):
        category = "Spam"
        reason = "Contains spammy keywords"
    elif any(w in body_text for w in ["please", "could you", "can you", "please review", "please confirm", "action", "deadline"]):
        category = "To-Do"
        reason = "Contains direct request or action language"
    else:
        category = "Important"
        reason = "Default fallback"

    actions = []
    for line in (email.get("body") or {}).get("text", "").splitlines() if isinstance(email.get("body"), dict) else str(email.get("body", "")).splitlines():
        low = line.strip().lower()
        if any(kw in low for kw in ["please", "could you", "can you", "please review", "please confirm", "action:", "todo"]):
            actions.append({"task": line.strip(), "deadline": None})

    if not actions and any(kw in subj for kw in ["task", "request", "todo", "please"]):
        actions.append({"task": subj, "deadline": None})

    return {
        **email,
        "category": category,
        "category_reason": reason,
        "action_items": actions
    }

def fetch_and_process_gmail(
    max_messages: int = 50,
    query: Optional[str] = None,
    mark_processed: bool = True,
    skip_processing: bool = False,
    simulate_processing: bool = False,
    sleep_between_calls: float = 0.05,
) -> List[Dict[str, Any]]:
    """
    Fetch messages from Gmail and process them.

    Args:
      max_messages: max messages to fetch
      query: optional Gmail search query (e.g., "is:unread -label:Processed")
      mark_processed: if True, add label "Processed" to messages
      skip_processing: if True, DO NOT call process_email (skip LLM calls)
      simulate_processing: if True and skip_processing==True, run a small heuristic simulator
    Returns:
      List of processed email dicts.
    """
    service = gmail_authenticate()
    ids = list_message_ids(service, query=query, max_results=max_messages)
    prompts = load_prompts()
    processed = []
    raw_saved = []
    label_id = create_label_if_not_exists(service, label_name="Processed")

    for msg_id in ids:
        msg = get_message(service, msg_id)
        if not msg:
            continue

        email_dict = {
            "id": msg.get("id"),
            "sender": msg.get("sender"),
            "subject": msg.get("subject"),
            "body": {
                "text": (msg.get("body") or {}).get("text") if isinstance(msg.get("body"), dict) else (msg.get("body") or ""),
                "html": (msg.get("body") or {}).get("html") if isinstance(msg.get("body"), dict) else None
            },
            "timestamp": msg.get("timestamp"),
            "raw_gmail": msg.get("raw_gmail", {})
        }

        raw_saved.append(email_dict)

        if skip_processing:
            if simulate_processing:
                updated = _simple_simulate_processing(email_dict)
            else:
                updated = email_dict
        else:
            try:
                updated = process_email(email_dict, prompts)
            except Exception as e:
                updated = {
                    **email_dict,
                    "category": "Unknown",
                    "category_reason": f"Processing error: {str(e)}",
                    "action_items": []
                }

        processed.append(updated)

        if mark_processed and label_id:
            try:
                add_label_to_message(service, msg_id, label_id)
            except Exception:
                pass

        if sleep_between_calls:
            time.sleep(sleep_between_calls)

    _save_raw_messages(raw_saved)
    return processed
