# app.py
import os
from pathlib import Path
import streamlit as st
from dotenv import load_dotenv
from bs4 import BeautifulSoup

# load .env so GEMINI_API_KEY (or other env vars) are available
load_dotenv()

# Import helper modules (must be in the same folder)
from agent_logic import (
    load_inbox,
    load_prompts,
    load_drafts,
    save_prompts,
    save_drafts,
    process_email,
    draft_reply,
    summarize_email,
)
from gmail_client import gmail_authenticate
from gmail_to_agent import fetch_and_process_gmail

# ---------- PAGE CONFIG ----------
st.set_page_config(page_title="Prompt-Driven Email Agent", layout="wide")

# ---------- SESSION STATE INITIALIZATION ----------
if "emails" not in st.session_state:
    try:
        st.session_state.emails = load_inbox()
    except Exception:
        st.session_state.emails = []

if "prompts" not in st.session_state:
    try:
        st.session_state.prompts = load_prompts()
    except Exception:
        st.session_state.prompts = {
            "categorization_prompt": "Categorize the following email into one of: Important, Newsletter, Spam, To-Do. Return JSON: { \"category\": \"...\", \"reason\": \"...\" }.",
            "action_item_prompt": "Extract tasks from the email. Return JSON array: [{\"task\": \"...\", \"deadline\": \"YYYY-MM-DD or null\"}].",
            "auto_reply_prompt": (
                "Draft a reply in tone {tone}. Return JSON: "
                "{ \"subject\": \"...\", \"body\": \"...\", \"suggested_followups\":[...] }."
            )
        }

if "drafts" not in st.session_state:
    try:
        st.session_state.drafts = load_drafts()
    except Exception:
        st.session_state.drafts = []

# convenience local refs
emails = st.session_state.emails
prompts = st.session_state.prompts
drafts = st.session_state.drafts

# ---------- SIDEBAR (Controls & Gmail integration) ----------
st.sidebar.title("Controls")

if st.sidebar.button("Reload Mock Inbox"):
    st.session_state.emails = load_inbox()
    st.sidebar.success("Mock inbox reloaded.")
    emails = st.session_state.emails

if st.sidebar.button("Process All Mock Emails"):
    with st.spinner("Processing mock inbox with prompts..."):
        new_emails = []
        for e in st.session_state.emails:
            updated = process_email(e, st.session_state.prompts)
            new_emails.append(updated)
        st.session_state.emails = new_emails
        emails = new_emails
    st.sidebar.success("Processing complete!")

st.sidebar.markdown("---")
st.sidebar.title("Gmail Integration")

if st.sidebar.button("Connect Gmail & Authenticate (OAuth)"):
    with st.spinner("Opening Google OAuth flow..."):
        try:
            service = gmail_authenticate()
            st.sidebar.success("Authenticated with Gmail! You can now fetch messages.")
        except Exception as e:
            st.sidebar.error(f"Auth failed: {e}")

# Processing mode toggle
st.sidebar.markdown("### Processing mode")
process_mode = st.sidebar.selectbox(
    "Choose how to process fetched Gmail messages:",
    options=["LLM (real)", "Simulate (heuristic)", "Skip processing"],
    index=0,
    help=(
        "LLM (real): call LLM for categorization & extraction (requires quota).\n"
        "Simulate: run local heuristic to produce categories/actions (no LLM).\n"
        "Skip processing: fetch raw messages without any processing."
    ),
)
st.sidebar.info(f"Current processing mode: **{process_mode}**")

query = st.sidebar.text_input("Gmail query (e.g., is:unread -label:Processed)", value="is:inbox -label:Processed")
max_msgs = st.sidebar.number_input("Max messages to fetch", min_value=1, max_value=200, value=50)

if st.sidebar.button("Fetch & Process Gmail"):
    # map selection to function flags
    if process_mode == "LLM (real)":
        skip_processing = False
        simulate_processing = False
    elif process_mode == "Simulate (heuristic)":
        skip_processing = True
        simulate_processing = True
    else:  # "Skip processing"
        skip_processing = True
        simulate_processing = False

    with st.spinner(f"Fetching messages from Gmail and processing ({process_mode})..."):
        try:
            processed = fetch_and_process_gmail(
                max_messages=max_msgs,
                query=query,
                mark_processed=True,
                skip_processing=skip_processing,
                simulate_processing=simulate_processing,
            )
            # Merge: add processed at top and keep other messages not duplicated
            processed_ids = {p.get("id") for p in processed}
            st.session_state.emails = processed + [e for e in st.session_state.emails if e.get("id") not in processed_ids]
            emails = st.session_state.emails
            st.sidebar.success(f"Fetched + processed {len(processed)} messages (mode: {process_mode}).")
        except Exception as e:
            st.sidebar.error(f"Fetch failed: {e}")

st.sidebar.markdown("---")
st.sidebar.info("Prompts can be edited in the Prompt Brain tab. Drafts are saved locally and never sent automatically.")

# ---------- MAIN UI TABS ----------
tab_inbox, tab_prompt, tab_agent, tab_drafts = st.tabs(
    ["📥 Inbox", "🧠 Prompt Brain", "🤖 Email Agent", "✉️ Drafts"]
)

# ---------- TAB: INBOX ----------
with tab_inbox:
    st.header("Inbox")
    if not st.session_state.emails:
        st.warning("No emails loaded. Use 'Reload Mock Inbox' or fetch from Gmail.")
    else:
        # layout: left list, right detail
        left_col, right_col = st.columns([1, 2])
        with left_col:
            st.subheader("Email List")
            # radio select shows id and subject
            email_ids = [e.get("id") for e in st.session_state.emails]
            # provide consistent sort by timestamp if available
            def format_fn(i):
                e = next((x for x in st.session_state.emails if x.get("id") == i), {})
                subj = e.get("subject", "(no subject)")
                sender = e.get("sender", "(unknown)")
                cat = e.get("category", "Not processed")
                return f"{i} — {subj} — {sender} — [{cat}]"

            selected_id = st.radio("Select an email:", options=email_ids, format_func=format_fn)

        with right_col:
            selected_email = next((e for e in st.session_state.emails if e.get("id") == selected_id), None)
            if not selected_email:
                st.write("Email not found.")
            else:
                st.subheader("Email Details")
                st.write(f"**From:** {selected_email.get('sender')}")
                st.write(f"**Subject:** {selected_email.get('subject')}")
                st.write(f"**Timestamp:** {selected_email.get('timestamp')}")
                st.write(f"**Category:** `{selected_email.get('category', 'Not processed')}`")

                # ---------- Clean Email Body Rendering (NO CODE BLOCKS) ----------
                st.markdown("**Body:**")
                body_info = selected_email.get("body") or {}

                # Support both dict-based body and old string body
                if isinstance(body_info, dict):
                    body_text = (body_info.get("text") or "") or ""
                    body_html = body_info.get("html", None)
                else:
                    body_text = str(body_info or "")
                    body_html = None

                # Clean body_text: remove leftover HTML tags or comments
                def clean_text(raw: str) -> str:
                    if not raw:
                        return ""
                    # Use BeautifulSoup to extract readable text if HTML fragments exist
                    soup = BeautifulSoup(raw, "html.parser")
                    for tag in soup(["script", "style"]):
                        tag.decompose()
                    text = soup.get_text(separator="\n")
                    # collapse multiple blank lines and strip
                    lines = [ln.strip() for ln in text.splitlines()]
                    cleaned = "\n\n".join([ln for ln in lines if ln])
                    return cleaned

                cleaned_text = clean_text(body_text)

                # Toggle for HTML rendering (sanitized HTML is provided by gmail_client)
                show_html = st.checkbox("Render formatted HTML (sanitized)", value=False)

                if show_html and body_html:
                    import streamlit.components.v1 as components
                    wrapped_html = f"""
                    <div style='font-family: Arial, Helvetica, sans-serif; line-height: 1.5; padding: 12px;'>
                        {body_html}
                    </div>
                    """
                    components.html(wrapped_html, height=500, scrolling=True)
                else:
                    # Show clean plain text as readable paragraphs using Markdown (no code block)
                    if cleaned_text.strip():
                        # preserve paragraphs: replace single newline with two spaces + newline for Markdown line breaks
                        md = cleaned_text.replace("\r\n", "\n")
                        # convert paragraph breaks to Markdown paragraph breaks
                        md = "\n\n".join([p.strip() for p in md.split("\n\n") if p.strip()])
                        st.markdown(md)
                    else:
                        # If nothing in text, but html exists, show readable fallback from html
                        if body_html:
                            fallback = clean_text(body_html)
                            st.markdown(fallback if fallback else "_(no readable text)_")
                        else:
                            st.markdown("_(no message body)_")

                st.markdown("**Category Reason:**")
                # show category reason as plain text (no code)
                reason = selected_email.get("category_reason", "")
                if reason:
                    st.markdown(reason)
                else:
                    st.markdown("_No category reason available._")

                st.markdown("**Action Items:**")
                items = selected_email.get("action_items")
                if items is None:
                    st.write("_Email not processed yet._")
                elif not items:
                    st.write("_No tasks extracted._")
                else:
                    for i, item in enumerate(items, start=1):
                        if isinstance(item, dict):
                            task = item.get("task", "")
                            dl = item.get("deadline")
                            if dl:
                                st.markdown(f"- **{i}.** {task} _(deadline: {dl})_")
                            else:
                                st.markdown(f"- **{i}.** {task}")
                        else:
                            st.markdown(f"- **{i}.** {str(item)}")

                # small quick actions for this email
                st.markdown("---")
                if st.button("Re-run processing for this email"):
                    with st.spinner("Running prompts on selected email..."):
                        updated = process_email(selected_email, st.session_state.prompts)
                        # replace in session list
                        st.session_state.emails = [updated if e.get("id") == updated.get("id") else e for e in st.session_state.emails]
                        st.experimental_rerun()

# ---------- TAB: PROMPT BRAIN ----------
with tab_prompt:
    st.header("Prompt Brain (Edit & Save)")
    st.write("Edit the prompts that drive ALL LLM behavior. Changes apply when you re-run processing.")
    cat_prompt = st.text_area("Categorization Prompt", value=st.session_state.prompts.get("categorization_prompt", ""), height=150)
    action_prompt = st.text_area("Action Item Prompt", value=st.session_state.prompts.get("action_item_prompt", ""), height=150)
    auto_prompt = st.text_area("Auto-Reply Draft Prompt", value=st.session_state.prompts.get("auto_reply_prompt", ""), height=150)

    if st.button("Save Prompts"):
        new_prompts = {
            "categorization_prompt": cat_prompt,
            "action_item_prompt": action_prompt,
            "auto_reply_prompt": auto_prompt
        }
        try:
            save_prompts(new_prompts)
            st.session_state.prompts = new_prompts
            st.success("Prompts saved to disk and session.")
        except Exception as e:
            st.error(f"Failed to save prompts: {e}")

    st.markdown("---")
    st.write("Tip: Make small edits and re-run processing on a single email to see effect before processing entire inbox.")

# ---------- TAB: EMAIL AGENT ----------
with tab_agent:
    st.header("Email Agent (Summarize, Extract, Draft)")

    if not st.session_state.emails:
        st.warning("No emails loaded.")
    else:
        agent_email_id = st.selectbox(
            "Select email for the agent:",
            options=[e.get("id") for e in st.session_state.emails],
            format_func=lambda i: f"{i}: {next((x for x in st.session_state.emails if x.get('id') == i), {}).get('subject','')}"
        )
        agent_email = next((e for e in st.session_state.emails if e.get("id") == agent_email_id), None)
        if agent_email:
            st.markdown(f"**Selected:** {agent_email.get('subject')}")
            st.markdown("### Quick Actions")
            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button("Summarize this email"):
                    with st.spinner("Summarizing..."):
                        try:
                            summary = summarize_email(agent_email)
                            st.markdown("**Summary:**")
                            st.markdown(summary)
                        except Exception as e:
                            st.error(f"Summarization failed: {e}")

            with c2:
                if st.button("Show extracted tasks (if processed)"):
                    if "action_items" not in agent_email:
                        st.warning("Email not processed yet. Run 'Process All Mock Emails' or 'Fetch & Process Gmail'.")
                    else:
                        st.markdown("**Extracted Tasks:**")
                        items = agent_email.get("action_items", [])
                        if not items:
                            st.write("_No tasks found._")
                        else:
                            for i, it in enumerate(items, start=1):
                                if isinstance(it, dict):
                                    st.markdown(f"- **{i}.** {it.get('task')} _(deadline: {it.get('deadline')})_")
                                else:
                                    st.markdown(f"- **{i}.** {it}")

            with c3:
                tone = st.selectbox("Reply tone", ["professional", "casual", "friendly"], key="reply_tone")
                if st.button("Draft a reply"):
                    with st.spinner("Drafting reply..."):
                        try:
                            reply = draft_reply(agent_email, st.session_state.prompts, tone=tone)
                            st.markdown("**Draft Subject:**")
                            st.write(reply.get("subject", ""))
                            st.markdown("**Draft Body:**")
                            st.write(reply.get("body", ""))
                            st.markdown("**Suggested Follow-ups:**")
                            for f in reply.get("suggested_followups", []):
                                st.markdown(f"- {f}")
                            # save draft locally
                            draft_record = {
                                "email_id": agent_email.get("id"),
                                "original_subject": agent_email.get("subject"),
                                "draft_subject": reply.get("subject", ""),
                                "draft_body": reply.get("body", ""),
                                "suggested_followups": reply.get("suggested_followups", []),
                            }
                            st.session_state.drafts.append(draft_record)
                            save_drafts(st.session_state.drafts)
                            st.success("Draft saved locally (not sent).")
                        except Exception as e:
                            st.error(f"Drafting failed: {e}")

# ---------- TAB: DRAFTS ----------
with tab_drafts:
    st.header("Saved Drafts (local)")
    if not st.session_state.drafts:
        st.write("No drafts yet.")
    else:
        for idx, d in enumerate(st.session_state.drafts, start=1):
            st.markdown(f"### Draft {idx}")
            st.write(f"**Original Email ID:** {d.get('email_id')}")
            st.write(f"**Original Subject:** {d.get('original_subject')}")
            st.write(f"**Draft Subject:** {d.get('draft_subject')}")
            st.write("**Draft Body:**")
            st.write(d.get("draft_body"))
            if d.get("suggested_followups"):
                st.write("**Suggested Follow-ups:**")
                for f in d.get("suggested_followups", []):
                    st.write(f"- {f}")
            st.markdown("---")

# ---------- FOOTER / HELPFUL LINKS ----------
st.markdown("---")
st.write(
    "Instructions: Use the Prompt Brain to change how the agent reasons. "
)
st.write(
    "Use 'Process All Mock Emails' to run prompts over sample inbox. "
)
st.write(
    "Use Gmail integration to fetch real messages."
)
