Prompt-Driven Email Agent

Streamlit app that connects to Gmail, ingests messages (real or mock), and performs LLM-powered tasks such as:

Email categorization

Action-item extraction

Auto-drafting replies

Chat / agent interactions with the inbox

The app ships with:

A Streamlit UI (app.py) — inbox / prompt brain / agent / drafts tabs

Gmail integration helpers (gmail_client.py, gmail_to_agent.py)

LLM glue in agent_logic.py (configured for Google Gemini)

Local test inbox & prompt storage under data/

Safe defaults so you can run without LLM quota (simulate/skip modes)

Project files

app.py — Streamlit front end (UI + sidebar controls)

gmail_client.py — Gmail API helpers + body extraction & sanitization

gmail_to_agent.py — fetch/process Gmail wrapper (skip/simulate flags)

agent_logic.py — LLM wrapper + processing logic (Gemini integration)

data/inbox.json — mock inbox (used by "Reload Mock Inbox")

data/prompts.json — saved prompt brain

data/drafts.json — saved local drafts

data/gmail_raw.json — saved raw fetches (created at runtime)

requirements.txt — Python dependencies (see below)

.gitignore — recommended ignore list

README.md — this file

Assignment PDF (uploaded): /mnt/data/Assignment - 2.pdf

Reviewer convenience: the assignment PDF included with this project is at /mnt/data/Assignment - 2.pdf.

Quick start (local)
1. Create & activate virtualenv
python -m venv venv
# Windows PowerShell
venv\Scripts\Activate.ps1
# or cmd
venv\Scripts\activate.bat
# macOS / Linux
source venv/bin/activate

2. Install dependencies
pip install -r requirements.txt


Suggested requirements.txt (example)

streamlit
google-auth
google-auth-oauthlib
google-api-python-client
beautifulsoup4
bleach
python-dotenv
google-generativeai
requests

3. Add secrets (do NOT commit)

Create a .env file in the project root (same folder as app.py) with these keys:

GEMINI_API_KEY=YOUR_GEMINI_API_KEY_HERE


Google OAuth: Download credentials.json (from Google Cloud Console) and place it in project root temporarily to run the OAuth flow. Do not commit credentials.json or token.json.

Add these to .gitignore:

.env
credentials.json
token.json
venv/

4. Run the app
streamlit run app.py


Open the URL printed by Streamlit (usually http://localhost:8501).

How to use the app
Sidebar controls

Reload Mock Inbox — load sample emails from data/inbox.json. Good for offline testing.

Process All Mock Emails — run prompt brain through all mock messages (uses the LLM pipeline if enabled).

Connect Gmail & Authenticate (OAuth) — start Google OAuth flow (one-time); stores token.json locally.

Processing mode — choose between:

LLM (real) — uses Gemini for processing (requires GEMINI_API_KEY)

Simulate (heuristic) — runs local heuristics (no LLM)

Skip processing — fetch only, no processing

Fetch & Process Gmail — fetches messages from your Gmail account (based on query) and processes them.

Tabs

Inbox — left column: message list. Right column: details, category, action items; optional “Render formatted HTML (sanitized)” toggle.

Prompt Brain — edit and save prompts that guide all LLM behavior. Save prompts to data/prompts.json.

Email Agent — summarization, show extracted tasks, draft replies. Note: these operations call the LLM unless using simulate mode or unless the backend was configured for a non-LLM fallback.

Drafts — locally saved drafts (not sent).

Gemini (LLM) setup

Create an API key in Google AI Studio (AI Studio → API keys).

Put key in .env:

GEMINI_API_KEY=sk-...


The project expects a model string present in agent_logic.py. If you used the included list models helper and found models, set:

MODEL_NAME = "models/gemini-2.5-flash"


or whichever models/… entry from the list output you want to use. (The code examples use the exact model name returned by the API—include the leading models/.)

Restart Streamlit after changes.

Running without paid LLM credits

If you do not want to use Gemini or OpenAI, pick Simulate (heuristic) in the sidebar before clicking Fetch & Process Gmail. The app will:

Fetch Gmail messages normally (OAuth still required)

Use local text heuristics to produce categories & action items for demo purposes
This makes a complete demo without any API key.
