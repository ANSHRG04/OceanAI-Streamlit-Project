# /mnt/data/gmail_client.py
import os
import base64
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request

# New imports for HTML cleaning / text extraction
from bs4 import BeautifulSoup
import bleach

# Put credentials.json (downloaded from Google Cloud) in project root
CREDS_PATH = Path("credentials.json")
TOKEN_PATH = Path("token.json")

# Scopes: we use gmail.modify so we can add labels
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

# Allowed tags/attributes for sanitized HTML rendering
ALLOWED_TAGS = [
    "a", "b", "i", "strong", "em", "p", "br", "ul", "ol", "li", "blockquote", "code", "pre",
    "h1", "h2", "h3", "h4", "table", "thead", "tbody", "tr", "td", "th", "img"
]
ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "rel", "target"],
    "img": ["src", "alt", "title", "width", "height"],
    "*": ["style"]
}


def gmail_authenticate() -> Any:
    """
    Returns an authorized Gmail API service object.
    This will open a local browser for OAuth on first run and save token.json.
    """
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(TOKEN_PATH, "w") as token_file:
            token_file.write(creds.to_json())

    service = build("gmail", "v1", credentials=creds)
    return service


def list_message_ids(service, user_id="me", query: Optional[str] = None, max_results: int = 100) -> List[str]:
    """
    Returns a list of Gmail message IDs. Optional Gmail search query supported.
    """
    try:
        response = service.users().messages().list(userId=user_id, q=query, maxResults=max_results).execute()
        msgs = response.get("messages", [])
        return [m["id"] for m in msgs]
    except HttpError as error:
        print("An error occurred listing messages:", error)
        return []


def get_message(service, msg_id: str, user_id="me") -> Dict[str, Any]:
    """
    Fetch a message and return dict with headers and body (as {'text','html'}) and raw message.
    """
    try:
        message = service.users().messages().get(userId=user_id, id=msg_id, format="full").execute()
    except HttpError as error:
        print("An error occurred fetching message:", error)
        return {}

    payload = message.get("payload", {})
    headers = payload.get("headers", [])
    header_dict = {h["name"].lower(): h["value"] for h in headers}

    subject = header_dict.get("subject", "(no subject)")
    sender = header_dict.get("from", "(unknown)")
    date = header_dict.get("date", "")
    # Extract body - returns dict {"text": "...", "html": "..." or None}
    body = extract_message_body(payload)

    return {
        "id": msg_id,
        "threadId": message.get("threadId"),
        "subject": subject,
        "sender": sender,
        "timestamp": date,
        "body": body,
        "raw_gmail": message  # full message if you need attachments/labels
    }


def _html_to_text(html: str) -> str:
    """Convert HTML to readable plain text using BeautifulSoup."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    # collapse blank lines and trim
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join([ln for ln in lines if ln])


def _extract_parts(part):
    """
    Recursively gather plain (text/plain) and html (text/html) parts from a message part.
    Returns (plain_parts_list, html_parts_list)
    """
    plain_parts = []
    html_parts = []

    mimeType = part.get("mimeType", "")
    body = part.get("body", {}) or {}

    if mimeType == "text/plain" and body.get("data"):
        try:
            data = base64.urlsafe_b64decode(body["data"].encode("ASCII")).decode("utf-8", errors="replace")
            plain_parts.append(data)
        except Exception:
            pass
    elif mimeType == "text/html" and body.get("data"):
        try:
            data = base64.urlsafe_b64decode(body["data"].encode("ASCII")).decode("utf-8", errors="replace")
            html_parts.append(data)
        except Exception:
            pass

    for sub in part.get("parts", []) or []:
        p, h = _extract_parts(sub)
        plain_parts.extend(p)
        html_parts.extend(h)

    return plain_parts, html_parts


def extract_message_body(payload) -> Dict[str, Optional[str]]:
    """
    Return a dict: {'text': '...', 'html': '... or None'}.

    - Prefer text/plain parts if present.
    - If no plain text exists but html exists, return a sanitized html (safe) and a plain-text fallback.
    - If neither exists, return empty strings.
    """
    # If payload has direct body (rare)
    if payload.get("body", {}).get("data"):
        try:
            raw = base64.urlsafe_b64decode(payload["body"]["data"].encode("ASCII")).decode("utf-8", errors="replace")
            return {"text": raw, "html": None}
        except Exception:
            pass

    plain_parts, html_parts = _extract_parts(payload)

    # If we have plain text parts, prefer them
    if plain_parts:
        text = "\n\n".join(plain_parts)
        html = "\n\n".join(html_parts) if html_parts else None
        # If html exists, sanitize it for optional rendering
        safe_html = bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES, strip=True) if html else None
        return {"text": text, "html": safe_html}

    # Fallback: if we have html but no plain text
    if html_parts:
        html = "\n\n".join(html_parts)
        safe_html = bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES, strip=True)
        text = _html_to_text(html)
        return {"text": text, "html": safe_html}

    return {"text": text, "html": safe_html}


def create_label_if_not_exists(service, label_name="Processed", user_id="me") -> str:
    """
    Create or return existing label id.
    """
    try:
        labels = service.users().labels().list(userId=user_id).execute().get("labels", [])
        for lbl in labels:
            if lbl.get("name") == label_name:
                return lbl["id"]
        label_body = {
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
            "name": label_name
        }
        label = service.users().labels().create(userId=user_id, body=label_body).execute()
        return label["id"]
    except HttpError as error:
        print("Error creating label:", error)
        return ""


def add_label_to_message(service, msg_id: str, label_id: str, user_id="me"):
    """Add label to a message (mark processed)."""
    try:
        service.users().messages().modify(userId=user_id, id=msg_id, body={"addLabelIds": [label_id]}).execute()
    except HttpError as error:
        print("Error adding label:", error)
