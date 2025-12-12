# main.py (IMPROVED)
# KUST BOTS OFFICIAL SUPPORT SYSTEM (Production Release - V4 KustX) - IMPROVED
# Single-File Flask Application with Server-Sent Events (SSE) Streaming
# Improvements:
#  - Robust session compression & persistence in-memory
#  - Offline mock inference mode (when INFERENCE env vars missing) for dev/testing
#  - Cleaner tool invocation flow
#  - Embedded owner / project knowledge (not salesy — clarifying tone)
#  - Better error handling and stable streaming parsing

import os
import re
import time
import json
import uuid
import logging
import requests
import sys
from flask import Flask, request, jsonify, Response, render_template_string, stream_with_context

# ----------------------------
# 1. Configuration & Logging
# ----------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] KUST: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout
)
logger = logging.getLogger("kust-support")

INFERENCE_KEY = os.getenv("INFERENCE_KEY", "").strip()
INFERENCE_MODEL_ID = os.getenv("INFERENCE_MODEL_ID", "").strip()
BASE_URL = os.getenv("INFERENCE_URL", "").strip()

MOCK_MODE = not (INFERENCE_KEY and INFERENCE_MODEL_ID and BASE_URL)
if MOCK_MODE:
    logger.warning("⚠️ INFERENCE env vars missing or empty — running in MOCK_MODE (offline simulation).")

API_URL = f"{BASE_URL.rstrip('/')}/v1/chat/completions" if BASE_URL else None
HEADERS = {"Authorization": f"Bearer {INFERENCE_KEY}", "Content-Type": "application/json"} if not MOCK_MODE else {}

logger.info(f"System Initialized. Model: {INFERENCE_MODEL_ID or 'MOCK'}")

# ----------------------------
# 2. Knowledge Base (Business Logic) & Owner Knowledge
# ----------------------------
# This KB is used by the bot's internal 'get_info' tool and as context for the assistant.
KB = {
    "projects": {
        "stake_chat_farmer": {
            "id": "stake_chat_farmer",
            "name": "Stake Chat Farmer",
            "access": "@kustchatbot",
            "price": "Free 3-hour trial",
            "short": "Automated, human-like chat activity to farm XP/levels. Not spam.",
            "features": [
                "Autonomous chat generator (not spammy)",
                "24/7 farming with multi-account support",
                "Configurable mood/timings"
            ],
            "setup": [
                "Start bot",
                "Link accounts",
                "Configure mood & limits",
                "Enable run"
            ]
        },
        "stake_code_claimer": {
            "id": "stake_code_claimer",
            "name": "Stake Code Claimer",
            "short": "Monitors channels and claims codes instantly across accounts.",
            "features": ["24/7 monitoring", "Multi-account claiming", "Low-latency actions"]
        },
        "frozen_music": {
            "id": "frozen_music",
            "name": "Frozen Music Bot",
            "short": "High-performance music bot with VC & video support.",
            "commands": ["/play", "/vplay", "/skip", "/couple", "/tmute"],
            "features": ["VC music", "Distributed backend", "Caching for instant playback"]
        },
        "kustify_hosting": {
            "id": "kustify_hosting",
            "name": "Kustify Hosting",
            "short": "Deploy bots via /host. Stopped bots cost 2 sparks/day.",
            "plans": {
                "Ember": "$1.44/mo (0.25 CPU/512MB)",
                "Flare": "$2.16/mo (0.5 CPU/1GB)",
                "Inferno": "$3.60/mo (1 CPU/2GB)"
            }
        },
        "custom_bots": {
            "id": "custom_bots",
            "name": "Paid Custom Bots",
            "short": "White-label and tailored solutions — development & support.",
            "pricing_note": "Example ranges: simple commands $2-$5 each; managed music bots $4-$20/mo depending on tier."
        }
    },
    "compliance": {
        "official": ["@kustbots", "@kustbotschat", "@KustDev", "@KustXoffical"],
        "warn": "Beware of fakes. We NEVER discuss gambling bonuses, drops, predictions, or promos."
    },
    # Quick contact & branding
    "brand": {
        "owner": "@KustDev",
        "main_channel": "@kustbots",
        "support_group": "@kustbotschat",
        "github": "kustbots",
        "preferred_name": "Kust"
    }
}

# ----------------------------
# 2.1 Embedded Owner Knowledge (from model context)
# ----------------------------
OWNER_KNOWLEDGE = {
    "preferred_name": "Kust",
    "main_channel": "@kustbots",
    "support_group": "@kustbotschat",
    "projects_highlight": [
        "Stake Chat Farmer",
        "Stake Code Claimer",
        "Frozen Music (VC) Bot",
        "Kustify Hosting",
        "Custom Bots & White-label services"
    ],
    "tech_stack": [
        "Cloudflare Workers for routing",
        "Flask and Python for APIs",
        "yt-dlp for media resolution",
        "Distributed playback nodes with caching",
    ],
    "current_work": [
        "Music streaming website (Frozen Music)",
        "YouTube audio/video downloader API",
        "Raspberry Pi cluster backend (35 nodes for testing)",
        "Valorant-like UE5 mobile shooter (1v1 testing)"
    ],
    "safety_rules": [
        "NEVER mention bonuses, drops, weekly/monthly gambling promotions.",
        "NEVER start a conversation with a moderator unless they initiate.",
        "Do not promote buying/selling/trades or request/send DMs for deals.",
        "Limit replies to at most TWO users in multi-user conversations."
    ],
    "user_preferences": {
        "tone": "helpful, clear, not too salesy",
        "language": "prefers simple English; may request Hindi occasionally"
    }
}

# ----------------------------
# 3. System Prompt (improved)
# ----------------------------
SYSTEM_PROMPT = f"""
You are KustX — official AI support for Kust Bots (owner: {KB['brand']['owner']}).

GOAL:
- Help users understand Kust Bots services.
- Clear doubts and fix misunderstandings; avoid sounding like a salesperson.
- Be short, precise, and helpful. If a user seems unsure, ask one clarifying question, then answer.
- When listing steps or features, use Markdown bullet lists with each item on a new line.
- Use plain/simple English by default. If the user explicitly requests Hindi, provide a short translation but prefer English.

CRITICAL RULES (ALWAYS ENFORCE):
- NEVER mention gambling bonuses, drops, predictions, or similar promos.
- NEVER start conversation with a moderator (marked [MODERATOR]) — only respond if they initiate.
- NEVER promote buying/selling/trading, or request/suggest DMs for deals.
- Only reply to at most TWO users in a multi-user session.
- Keep content legal, safe, and professional.

KNOWLEDGE (owner & services):
- Preferred name: {OWNER_KNOWLEDGE['preferred_name']}
- Channels: {KB['brand']['main_channel']}, {KB['brand']['support_group']}
- Key services: {', '.join(OWNER_KNOWLEDGE['projects_highlight'])}
- Tech highlights: {', '.join(OWNER_KNOWLEDGE['tech_stack'])}
- Current work examples: {', '.join(OWNER_KNOWLEDGE['current_work'])}

TOOLS:
- Use a tool named `get_info` to fetch structured information from an internal KB (returns JSON as text).
  Example tool call (assistant must output EXACT JSON): {{ "tool": "get_info", "query": "services" }}

FALLBACK:
- If you do not know something, say "I don't have that info" and offer a safe next step (link to {KB['brand']['main_channel']} or ask for more details).
"""

# ----------------------------
# 4. Flask App & Session Management
# ----------------------------
app = Flask(__name__)
SESSIONS = {}  # in-memory sessions: sid -> list of messages (system/user/assistant)

def get_session(sid: str):
    """
    Ensure a session exists with the preserved system prompt at index 0.
    """
    if not sid:
        sid = str(uuid.uuid4())
    if sid not in SESSIONS:
        SESSIONS[sid] = [{"role": "system", "content": SYSTEM_PROMPT}]
    # if system prompt is missing (safety), ensure it's there
    if not SESSIONS[sid] or SESSIONS[sid][0].get("role") != "system":
        SESSIONS[sid].insert(0, {"role": "system", "content": SYSTEM_PROMPT})
    return SESSIONS[sid]

# ----------------------------
# 5. Tool Implementations
# ----------------------------
def search_kb(query: str):
    """
    Lightweight KB search returning a concise summary.
    """
    q = (query or "").strip().lower()
    if not q:
        return json.dumps({"error": "empty query"})

    # Broad queries map to service summary
    broad_triggers = ["service", "services", "what do you offer", "products", "offerings", "help", "features"]
    if any(t in q for t in broad_triggers):
        out = {"services": []}
        for k, v in KB["projects"].items():
            out["services"].append({
                "id": v.get("id", k),
                "name": v.get("name"),
                "short": v.get("short") or v.get("info") or "",
                "features": v.get("features", []),
            })
        out["compliance"] = KB["compliance"]
        out["brand"] = KB["brand"]
        return json.dumps(out)

    # Specific service match
    for k, v in KB["projects"].items():
        name = v.get("name", "").lower()
        if q in k or q in name or any(tok in name for tok in q.split()):
            result = {"id": v.get("id", k), "name": v.get("name"), "detail": v}
            return json.dumps(result)

    # If "official" or "fake" appear
    if "official" in q or "fake" in q or "authentic" in q:
        return json.dumps({"compliance": KB["compliance"]})

    # fallback: return helpful hint
    return json.dumps({"note": "No record found", "advice": "Ask about specific services like 'Frozen Music' or 'Kustify Hosting'."})

# The external-tool wrapper expected by the system prompt (JSON-only tool calls).
def run_tool(tool_json):
    """
    Expecting a dict like {"tool": "get_info", "query": "services"}
    """
    try:
        tool = tool_json.get("tool")
        query = tool_json.get("query", "")
        if tool == "get_info":
            return search_kb(query)
        else:
            return json.dumps({"error": f"tool {tool} not supported"})
    except Exception as e:
        logger.exception("Tool execution failed")
        return json.dumps({"error": "tool execution error"})

# ----------------------------
# 6. Inference / Streaming (real + mock)
# ----------------------------
def mock_inference_stream(messages):
    """
    Simple offline streaming responder for development and testing.
    Produces reasonable helpful replies referencing KB and OWNER_KNOWLEDGE.
    Emits small chunks to mimic streaming.
    """
    last_user = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user = m.get("content", "")
            break
    last_user_lower = (last_user or "").lower()
    response_text = ""

    # If user asked for services, emit a tool call JSON first (per system prompt)
    if any(w in last_user_lower for w in ["what do you offer", "services", "what services", "what do you have", "show me services", "help me with services"]):
        # Direct tool JSON output (assistant must output only JSON for tool usage)
        tool_json = {"tool": "get_info", "query": "services"}
        yield json.dumps({"type": "tool_json", "content": json.dumps(tool_json)})
        # simulate tool execution animation
        time.sleep(0.2)
        tool_result = run_tool(tool_json)
        # After tool, produce a human-friendly summary:
        parsed = json.loads(tool_result)
        services_list = []
        for s in parsed.get("services", []):
            services_list.append(f"- **{s.get('name')}**: {s.get('short')}")
        response_text = "I found these services:\n\n" + "\n".join(services_list) + "\n\nIf you want details about any one, ask 'Tell me about <service name>'."
    else:
        # Heuristic replies
        if "hosting" in last_user_lower or "kustify" in last_user_lower:
            response_text = ("Kustify Hosting plans are simple. You can deploy with /host. Example plans:\n\n"
                             "- Ember: $1.44/mo (0.25 CPU/512MB)\n- Flare: $2.16/mo (0.5 CPU/1GB)\n- Inferno: $3.60/mo (1 CPU/2GB)\n\n"
                             "Tell me what you plan to run and I can recommend a plan.")
        elif "music" in last_user_lower or "frozen" in last_user_lower:
            response_text = ("Frozen Music Bot commands: " + ", ".join(KB['projects']['frozen_music'].get('commands', [])) +
                             "\n\nIt runs on a distributed backend with caching. Ask setup or troubleshooting questions.")
        elif "claim" in last_user_lower or "code" in last_user_lower:
            response_text = ("Stake Code Claimer monitors channels and claims codes across accounts. "
                             "It is intended to be fast and low-latency — ask about multi-account setup or limits.")
        else:
            # generic helpful fallback
            response_text = ("I can help with questions about our services, setup steps, or account linking.\n\n"
                             "Quick tips:\n- Say 'Show me services' to get a list.\n- Ask 'How do I setup <service>' for step-by-step help.\n\n"
                             f"If you'd like a short Hindi translation for any reply, say so and I'll provide it.")

    # stream the response in small chunks
    i = 0
    chunk_size = 60
    while i < len(response_text):
        chunk = response_text[i:i+chunk_size]
        yield json.dumps({"type": "token", "content": chunk})
        time.sleep(0.03)
        i += chunk_size

    # done token
    yield json.dumps({"type": "done"})

def call_inference_stream(messages):
    """
    If real inference configured, stream from the remote API.
    Otherwise fall back to mock_inference_stream which uses internal KB.
    This function yields plain dict-like events encoded as JSON strings (caller expects them).
    """
    if MOCK_MODE:
        # Mock path: yields JSON lines
        for evt in mock_inference_stream(messages):
            # mock emits JSON strings for each event
            yield f"data: {evt}\n\n"
        return

    # Real inference path (streaming)
    payload = {
        "model": INFERENCE_MODEL_ID,
        "messages": messages,
        "stream": True,
        "temperature": 0.5
    }

    try:
        with requests.post(API_URL, json=payload, headers=HEADERS, stream=True, timeout=60) as r:
            if r.status_code != 200:
                logger.error(f"Inference API returned {r.status_code} {r.text[:200]}")
                yield f"data: {json.dumps({'type': 'error', 'content': f'API Error {r.status_code}'})}\n\n"
                return

            # Buffer to collect tool-json if assistant emits it as first thing
            collecting_tool_json = False
            tool_buffer = ""

            for line in r.iter_lines(decode_unicode=True):
                if not line:
                    continue
                # Many streaming endpoints send "data: {...}" lines or raw JSON — normalize
                raw = line.strip()
                # If the server sent "data: [DONE]" style
                if raw == 'data: [DONE]' or raw == '[DONE]':
                    break

                # Attempt to parse actual JSON object from the chunk (robust)
                try:
                    if raw.startswith("data:"):
                        payload_text = raw[len("data:"):].strip()
                    else:
                        payload_text = raw

                    chunk_json = json.loads(payload_text)
                    # The exact structure differs by provider; we try to extract delta content
                    choices = chunk_json.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        token = delta.get("content")
                        if token:
                            yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
                        # check for tool call encoded as JSON content (assistant asked to call a tool)
                        # sometimes tool requests come as assistant content that is entire JSON object
                        if isinstance(token, str):
                            stripped = token.strip()
                            if stripped.startswith("{") and '"tool"' in stripped:
                                # collect full JSON
                                try:
                                    tool_json = json.loads(stripped)
                                    # run tool
                                    tool_result = run_tool(tool_json)
                                    # front-end animation toggles
                                    yield f"data: {json.dumps({'type': 'tool_start', 'tool': tool_json.get('tool'), 'input': tool_json.get('query')})}\n\n"
                                    time.sleep(0.3)
                                    yield f"data: {json.dumps({'type': 'tool_end', 'result': 'Done'})}\n\n"
                                    # inject tool result back by making a new assistant turn via recursion
                                    new_messages = messages + [{"role": "assistant", "content": stripped}, {"role": "user", "content": f"TOOL RESULT: {tool_result}"}]
                                    # recursion (small) to continue streaming
                                    for evt in call_inference_stream(new_messages):
                                        yield evt
                                    return
                                except Exception:
                                    # not critical; pass token as usual
                                    pass
                    else:
                        # If server uses a different structure, try text field
                        content = chunk_json.get("content") or chunk_json.get("text")
                        if content:
                            yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"

                except json.JSONDecodeError:
                    # Not a JSON chunk — send raw
                    raw_text = raw
                    yield f"data: {json.dumps({'type': 'token', 'content': raw_text})}\n\n"
                except Exception as e:
                    logger.exception("Error while parsing streaming chunk")
                    yield f"data: {json.dumps({'type': 'error', 'content': 'Stream parsing error'})}\n\n"

    except requests.exceptions.RequestException as e:
        logger.exception("Network error with inference API")
        yield f"data: {json.dumps({'type': 'error', 'content': 'Connection error to inference API'})}\n\n"
    except Exception as e:
        logger.exception("Unexpected streaming error")
        yield f"data: {json.dumps({'type': 'error', 'content': 'Unexpected stream error'})}\n\n"

# ----------------------------
# 7. Routes
# ----------------------------
@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/chat/stream", methods=["POST"])
def chat_stream():
    data = request.json or {}
    user_msg = data.get("message", "").strip()
    sid = data.get("session_id") or str(uuid.uuid4())

    if not user_msg:
        return jsonify({"error": "No message"}), 400

    history = get_session(sid)
    # append user message
    history.append({"role": "user", "content": user_msg})

    # CONTEXT COMPRESSION / SUMMARIZATION LOGIC
    # Keep system prompt + last 8 messages to limit context size
    if len(history) > 9:
        # preserve system prompt at index 0
        history = [history[0]] + history[-8:]
        SESSIONS[sid] = history  # update stored session
        logger.info(f"Session {sid[:8]} context optimized.")
    else:
        SESSIONS[sid] = history

    def generate():
        # initial ping
        yield f"data: {json.dumps({'type': 'ping'})}\n\n"

        full_text = ""
        # stream from inference (real or mock)
        for chunk in call_inference_stream(history):
            # chunk comes as "data: <jsonstr>\n\n"
            yield chunk
            # try to collect assistant text tokens for session storage
            try:
                raw = chunk[len("data: "):].strip()
                ev = json.loads(raw)
                if ev.get("type") == "token":
                    full_text += ev.get("content", "")
            except Exception:
                pass

        # If we collected assistant text and it's not a pure tool JSON, add to history
        if full_text and not full_text.strip().startswith("{"):
            SESSIONS[sid].append({"role": "assistant", "content": full_text})

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

@app.route("/api/reset", methods=["POST"])
def reset():
    sid = (request.json or {}).get("session_id")
    if sid and sid in SESSIONS:
        del SESSIONS[sid]
    new_id = str(uuid.uuid4())
    return jsonify({"status": "cleared", "new_id": new_id})

# ----------------------------
# 8. Frontend (unchanged - preserved UX)
# ----------------------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>KUSTX | Support Terminal</title>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Inter:wght@300;400;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #050505; --panel: #0f0f13; --border: #27272a;
            --primary: #3b82f6; --accent: #8b5cf6; --text: #e4e4e7;
            --text-dim: #a1a1aa; --tool-bg: #1e1e24; --success: #10b981;
        }
        * { box-sizing: border-box; }
        body { margin: 0; padding: 0; background: var(--bg); color: var(--text); font-family: 'Inter', sans-serif; height: 100vh; display: flex; overflow: hidden; }
        .sidebar { width: 300px; background: var(--panel); border-right: 1px solid var(--border); padding: 24px; display: flex; flex-direction: column; gap: 20px; }
        @media(max-width: 768px) { .sidebar { display: none; } }
        .brand { font-family: 'JetBrains Mono', monospace; font-weight: 700; font-size: 1.2rem; color: #fff; letter-spacing: -1px; display: flex; align-items: center; gap: 10px; }
        .brand span { color: var(--primary); }
        .status-box { padding: 12px; background: rgba(255,255,255,0.03); border-radius: 8px; border: 1px solid var(--border); font-size: 0.85rem; }
        .status-indicator { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 8px; }
        .status-indicator.live { background: var(--success); box-shadow: 0 0 10px var(--success); }
        .status-indicator.busy { background: var(--accent); animation: pulse 1s infinite; }
        .quick-actions { display: flex; flex-direction: column; gap: 8px; }
        .action-btn { background: transparent; border: 1px solid var(--border); color: var(--text-dim); padding: 10px; border-radius: 6px; cursor: pointer; text-align: left; transition: all 0.2s; font-size: 0.9rem; }
        .action-btn:hover { border-color: var(--primary); color: #fff; background: rgba(59,130,246,0.1); }
        .main { flex: 1; display: flex; flex-direction: column; position: relative; }
        .chat-container { flex: 1; padding: 20px; overflow-y: auto; display: flex; flex-direction: column; gap: 20px; scroll-behavior: smooth; }
        .message { max-width: 800px; margin: 0 auto; width: 100%; display: flex; gap: 16px; opacity: 0; animation: fadeIn 0.3s forwards; }
        .message.user { justify-content: flex-end; }
        .avatar { width: 36px; height: 36px; border-radius: 8px; background: var(--panel); border: 1px solid var(--border); display: flex; align-items: center; justify-content: center; font-size: 1.2rem; flex-shrink: 0; }
        .message.user .avatar { order: 2; background: var(--primary); border-color: var(--primary); color: white; }
        .bubble { background: var(--panel); border: 1px solid var(--border); padding: 12px 18px; border-radius: 12px; font-size: 0.95rem; line-height: 1.6; position: relative; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); }
        .message.user .bubble { background: var(--primary); color: white; border-color: var(--primary); text-align: right; }
        
        .tool-card { max-width: 800px; margin: 0 auto; background: var(--tool-bg); border: 1px solid var(--accent); border-left: 4px solid var(--accent); padding: 10px 16px; border-radius: 6px; color: #d8b4fe; font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; display: flex; align-items: center; gap: 12px; animation: slideIn 0.4s ease-out; margin-bottom: -10px; }
        .tool-spinner { width: 14px; height: 14px; border: 2px solid rgba(139, 92, 246, 0.3); border-top-color: var(--accent); border-radius: 50%; animation: spin 1s linear infinite; }
        
        .bubble p { margin: 0 0 10px 0; } .bubble p:last-child { margin: 0; }
        .bubble ul { padding-left: 20px; margin: 10px 0; } .bubble li { margin-bottom: 6px; }
        .bubble code { background: rgba(0,0,0,0.3); padding: 2px 5px; border-radius: 4px; font-family: 'JetBrains Mono', monospace; font-size: 0.9em; }
        
        .input-area { padding: 20px; background: rgba(5,5,5,0.9); border-top: 1px solid var(--border); backdrop-filter: blur(10px); }
        .input-wrapper { max-width: 800px; margin: 0 auto; position: relative; display: flex; gap: 10px; }
        input { width: 100%; background: var(--panel); border: 1px solid var(--border); padding: 14px 18px; border-radius: 10px; color: white; font-family: inherit; font-size: 1rem; outline: none; transition: border-color 0.2s; }
        input:focus { border-color: var(--primary); }
        button.send { background: var(--primary); color: white; border: none; padding: 0 24px; border-radius: 10px; font-weight: 600; cursor: pointer; transition: opacity 0.2s; }
        button.send:disabled { opacity: 0.5; cursor: not-allowed; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes slideIn { from { opacity: 0; transform: translateX(-20px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.4; } 100% { opacity: 1; } }
        .thinking { display: flex; gap: 4px; padding: 4px; }
        .dot { width: 6px; height: 6px; background: var(--text-dim); border-radius: 50%; animation: bounce 1.4s infinite ease-in-out both; }
        .dot:nth-child(1) { animation-delay: -0.32s; } .dot:nth-child(2) { animation-delay: -0.16s; }
        @keyframes bounce { 0%, 80%, 100% { transform: scale(0); } 40% { transform: scale(1); } }
    </style>
</head>
<body>
    <div class="sidebar">
        <div class="brand"><span>//</span> KUSTX</div>
        <div class="status-box"><div id="status-dot" class="status-indicator live"></div><span id="status-text">System Online</span></div>
        <div class="quick-actions">
            <div style="font-size:0.75rem; color:var(--text-dim); text-transform:uppercase; letter-spacing:1px; margin-bottom:4px;">Quick Access</div>
            <button class="action-btn" onclick="ask('What is Kustify Hosting pricing?')">💰 Hosting Plans</button>
            <button class="action-btn" onclick="ask('How do I setup the Stake Chat Farmer?')">🤖 Stake Farmer Setup</button>
            <button class="action-btn" onclick="ask('Show me commands for Frozen Music Bot')">🎵 Music Bot Cmds</button>
        </div>
        <div style="margin-top:auto; font-size:0.75rem; color:var(--text-dim);">Session ID: <span id="sess-id" style="font-family:monospace">...</span><br><a href="#" onclick="resetSession()" style="color:var(--accent)">Reset Session</a></div>
    </div>
    <div class="main">
        <div class="chat-container" id="chat">
            <div class="message"><div class="avatar">🤖</div><div class="bubble"><p><strong>KustX Online.</strong></p><p>I am KustX. How can I help you?</p></div></div>
        </div>
        <div class="input-area">
            <div class="input-wrapper"><input type="text" id="userInput" placeholder="Type your issue..." autocomplete="off"><button class="send" id="sendBtn" onclick="sendMessage()">SEND</button></div>
        </div>
    </div>
<script>
    const uuid = () => Math.random().toString(36).substring(2) + Date.now().toString(36);
    let session_id = localStorage.getItem('kust_sid') || uuid();
    localStorage.setItem('kust_sid', session_id);
    document.getElementById('sess-id').innerText = session_id.substring(0,8);
    const chatEl = document.getElementById('chat');
    const inputEl = document.getElementById('userInput');
    const sendBtn = document.getElementById('sendBtn');
    const statusDot = document.getElementById('status-dot');
    const statusText = document.getElementById('status-text');

    let activeToolEl = null;

    function setBusy(busy) {
        if(busy) { statusDot.className = 'status-indicator busy'; statusText.innerText = 'Processing...'; sendBtn.disabled = true; inputEl.disabled = true; } 
        else { statusDot.className = 'status-indicator live'; statusText.innerText = 'System Online'; sendBtn.disabled = false; inputEl.disabled = false; inputEl.focus(); }
    }
    function appendUserMsg(text) {
        const div = document.createElement('div'); div.className = 'message user'; div.innerHTML = `<div class="bubble">${text}</div><div class="avatar">👤</div>`; chatEl.appendChild(div); scrollToBottom();
    }
    function createBotMsg() {
        const div = document.createElement('div'); div.className = 'message'; div.innerHTML = `<div class="avatar">🤖</div><div class="bubble"><div class="thinking"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div></div>`; chatEl.appendChild(div); scrollToBottom(); return div.querySelector('.bubble');
    }
    function createToolCard(toolName) {
        const div = document.createElement('div'); div.className = 'tool-card'; div.innerHTML = `<div class="tool-spinner"></div> <span>Executing: ${toolName}...</span>`; 
        chatEl.insertBefore(div, chatEl.lastElementChild); scrollToBottom(); 
        return div;
    }
    function scrollToBottom() { chatEl.scrollTop = chatEl.scrollHeight; }

    async function sendMessage() {
        const text = inputEl.value.trim(); if(!text) return;
        inputEl.value = ''; appendUserMsg(text); setBusy(true);
        const botBubble = createBotMsg();
        let currentText = ""; let isFirstToken = true;

        try {
            const response = await fetch('/chat/stream', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ message: text, session_id: session_id })
            });
            const reader = response.body.getReader(); const decoder = new TextDecoder();

            while (true) {
                const { done, value } = await reader.read(); if (done) break;
                const chunk = decoder.decode(value); const lines = chunk.split('\\n\\n');
                for (const line of lines) {
                    if (!line) continue;
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.substring(6));
                            if (data.type === 'ping') continue;
                            if (data.type === 'tool_start') {
                                activeToolEl = createToolCard(data.input || data.tool);
                                continue;
                            }
                            if (data.type === 'tool_end') {
                                if(activeToolEl) activeToolEl.remove();
                                activeToolEl = null;
                                continue;
                            }
                            if (data.type === 'tool_json') {
                                // Assistant requested an internal tool. Frontend should show a tool card; backend will run it.
                                activeToolEl = createToolCard('internal tool');
                                continue;
                            }
                            if (data.type === 'token') {
                                if (isFirstToken) { botBubble.innerHTML = ''; isFirstToken = false; }
                                currentText += data.content; botBubble.innerHTML = marked.parse(currentText); scrollToBottom();
                                continue;
                            }
                            if (data.type === 'error') {
                                botBubble.innerHTML = `<span style="color:#ef4444">Error: ${data.content}</span>`;
                                continue;
                            }
                            if (data.type === 'done') {
                                if(activeToolEl) activeToolEl.remove();
                                activeToolEl = null;
                                break;
                            }
                        } catch (e) {
                            // ignore parse errors (partial chunk)
                        }
                    }
                }
            }
        } catch (err) { botBubble.innerHTML = "Connection failed."; console.error(err); } finally { setBusy(false); }
    }
    function ask(q) { inputEl.value = q; sendMessage(); }
    async function resetSession() { if(confirm("Clear chat?")) { await fetch('/api/reset', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({session_id})}); location.reload(); } }
    inputEl.addEventListener('keypress', (e) => { if (e.key === 'Enter') sendMessage(); });
</script>
</body>
</html>
"""

# ----------------------------
# 9. Runner
# ----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"Server starting on port {port} (MOCK_MODE={MOCK_MODE})")
    app.run(host="0.0.0.0", port=port, threaded=True)
