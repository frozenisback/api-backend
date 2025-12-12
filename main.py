# main.py
# KUST BOTS OFFICIAL SUPPORT SYSTEM (Production Release - V4 KustX)
# Single-File Flask Application with Server-Sent Events (SSE) Streaming
# Features: Natural AI, Robust Search, Auto-Cleaning UI, Smart Context.

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

INFERENCE_KEY = os.getenv("INFERENCE_KEY", "")
INFERENCE_MODEL_ID = os.getenv("INFERENCE_MODEL_ID", "")
BASE_URL = os.getenv("INFERENCE_URL", "")

if not (INFERENCE_KEY and INFERENCE_MODEL_ID and BASE_URL):
    logger.error("⚠️ CRITICAL: Missing INFERENCE env vars.")

API_URL = f"{BASE_URL.rstrip('/')}/v1/chat/completions"
HEADERS = {
    "Authorization": f"Bearer {INFERENCE_KEY}",
    "Content-Type": "application/json"
}

logger.info(f"System Initialized. Model: {INFERENCE_MODEL_ID}")

# ----------------------------
# 2. Knowledge Base (Business Logic)
# ----------------------------
KB = {
    "projects": {
        "stake_chat_farmer": {
            "display_name": "AI Stake Chat Farmer",
            "access": "@kustchatbot",
            "description": "Human-like autonomous chat emulator for Stake servers. Includes setup video in Hindi.",
            "price": "Free trial available. Paid subscriptions via Crypto or UPI.",
            "features": [
                "Per-user memory & topic tracking",
                "Mood adaptation & tone shifting",
                "Context-aware replies with mention handling",
                "Smart timing & human delay simulation",
                "Per-chat awareness (avoids repeating spam)",
                "Multi-account farming at scale",
                "24/7 autonomous operation"
            ],
            "setup": [
                "1. Go to @kustchatbot.",
                "2. New users: Click 'Get your trial now'.",
                "3. Enter your REAL Stake username (Case Sensitive).",
                "4. Bot sends an unpacked extension (.zip). Download and unzip it.",
                "5. Open Chrome, go to `chrome://extensions`, enable 'Developer Mode'.",
                "6. Click 'Load Unpacked' and select the unzipped folder.",
                "7. Go to Stake.com (or mirror like https://stake.com/casino/games/mines).",
                "8. Click the extension icon to enable it, then REFRESH the page.",
                "9. Look for the Chat Farmer popup on the left side.",
                "10. Click the 'Enable AI' button to start farming."
            ],
            "subscription": [
                "If trial is over:",
                "1. Go to @kustchatbot and send `/start`.",
                "2. Click 'Buy Subscription'.",
                "3. Enter your Stake username.",
                "4. Choose Payment:",
                "   - Crypto: Automated via OxaPay.",
                "   - UPI: Processed manually."
            ],
            "support_notes": [
                "User must provide real Stake username (Case Sensitive).",
                "Extension requires Developer Mode in Chrome.",
                "Must refresh Stake page after enabling extension."
            ]
        },
        "stake_code_claimer": {
            "display_name": "Stake Code Claimer",
            "description": "Monitors Stake Telegram channels in real time and instantly redeems codes.",
            "features": [
                "24/7 execution",
                "Realtime channel scraping",
                "Instant multi-account redemption",
                "Channel whitelist/blacklist"
            ],
            "support_notes": [
                "Ask for monitored channel links and account list",
                "Fix: Update parsing regex if format changes"
            ]
        },
        "frozen_music": {
            "display_name": "Frozen Music Bot",
            "description": "High-performance VC music bot with distributed backend.",
            "commands": [
                "/play",
                "/vplay",
                "/skip",
                "/pause",
                "/resume",
                "/stop",
                "/playlist",
                "/couple",
                "/tmute",
                "/mute",
                "/unmute",
                "/kick",
                "/ban",
                "/unban",
                "/ping",
                "/clear"
            ],
            "features": [
                "Multi-source streaming (YT/Spotify/Resso/Apple/SC)",
                "Video playback with vplay",
                "Distributed multi-node backend",
                "Auto-suggestions after queue ends",
                "Daily cached couple system"
            ],
            "limits": {
                "max_duration_seconds": 7800,
                "auto_fallback": True
            },
            "support_notes": [
                "Ask for: command used, chat ID, error screenshot",
                "Fix: Restart playback node, clear queue, re-cache metadata"
            ]
        },
        "kustify_hosting": {
            "display_name": "Kustify Hosting",
            "bot": "@kustifybot",
            "description": "Affordable Telegram bot hosting with instant deployment.",
            "plans": {
                "Ember": "0.25 CPU / 512MB RAM — $1.44/month",
                "Flare": "0.5 CPU / 1GB RAM — $2.16/month",
                "Inferno": "1 CPU / 2GB RAM — $3.60/month"
            },
            "billing": {
                "standby_cost": "2 sparks/day when bot is stopped"
            },
            "commands": [
                "/host",
                "/mybots",
                "/balance",
                "/buysparks",
                "/logs",
                "/env",
                "/restart",
                "/stop",
                "/resume",
                "/delete"
            ],
            "support_notes": [
                "Ask for instance ID + last logs",
                "Fix: Increase RAM if OOM, rotate environment variables"
            ]
        },
        "custom_bots": {
            "display_name": "Paid Custom Bots",
            "description": "Custom Telegram bots and white-label music bots.",
            "pricing": {
                "commands": "$2–$5 per command depending on complexity",
                "music_bots": [
                    "Tier 1: $4/mo + $6 setup (4–5 VCs)",
                    "Tier 2: $8/mo + $10 setup (~15 VCs)",
                    "Tier 3: $20/mo + $25 setup (~50 VCs)"
                ]
            },
            "support_notes": [
                "Collect full requirements/specification from user",
                "Deliver staging bot + testing instructions"
            ]
        }
    },

    "brand": {
        "official_channel": "@kustbots",
        "official_support_group": "@kustbotschat",
        "owner": "@KustDev",
        "note": "Any other channels or accounts claiming to be Kust Bots are fake."
    },

    "compliance": {
        "official": ["@kustbots", "@kustbotschat", "@KustDev"],
        "warn": "Beware of fakes. We NEVER discuss gambling bonuses, drops, predictions or promotions.",
        "rules": [
            "Never discuss bonuses, drops, weekly/monthly rewards.",
            "Never start a conversation with a moderator (reply only).",
            "Never promote or request any transactions.",
            "Respond to maximum 2 users at once.",
            "Keep timing natural."
        ]
    },

    "support_templates": {
        "verify": "Please confirm you're contacting us through @kustbots or @kustbotschat.",
        "request_logs": "Send: bot username, chat ID, exact command, and a screenshot of error/logs.",
        "trial_full": "Trial slots are currently full. You may join the waiting list.",
        "billing": "We support PayPal and manual processing for Indian clients."
    },

    "troubleshooting": {
        "music": {
            "issues": ["no audio", "stuttering", "video not playing"],
            "solutions": [
                "Check CDN audio URL validity",
                "Restart playback node",
                "Clear group queue and retry",
                "Check if yt-dlp fallback server is reachable"
            ]
        },
        "hosting": {
            "issues": ["instance fails to boot", "OOM crash", "build errors"],
            "solutions": [
                "Check /logs for build errors",
                "Upgrade to higher RAM plan",
                "Reset environment variables",
                "Redeploy clean"
            ]
        },
        "stake_tools": {
            "issues": ["redeem fails", "bot blocked", "anti-bot triggers"],
            "solutions": [
                "Rotate proxy/session",
                "Reduce frequency / increase jitter",
                "Fix bad regex or outdated code format",
                "Re-authenticate accounts"
            ]
        }
    }
}


SYSTEM_PROMPT = """
You are KustX, the official AI support for Kust Bots.

**IDENTITY:**
- Name: KustX
- Owner: @KustDev
- Official Channel: @kustbots

**BEHAVIOR:**
1. **Natural & Helpful:** Speak naturally. Be professional but not robotic. You don't need to be extremely brief, but don't ramble.
2. **Formatting:** IMPORTANT: When listing features, plans, or steps, ALWAYS use Markdown bullet points with each item on a NEW LINE.
3. **Guardrails:** If asked about coding general apps, essays, math, or competitors, politely decline: "I specialize in Kust Bots services only."
4. **Tool Use:** Use the `get_info` tool to fetch data. Output ONLY JSON for tools.
   - Example: {"tool": "get_info", "query": "pricing"}
   - Do NOT say "Let me check" before the JSON. Just output the JSON.

**DATA ACCESS:**
- If the user asks generally about "services", "products", or "what do you offer", use the `get_info` tool with the query "services".
"""

# ----------------------------
# 3. Flask App & Session Management
# ----------------------------
app = Flask(__name__)
SESSIONS = {}

def get_session(sid):
    if sid not in SESSIONS:
        SESSIONS[sid] = [{"role": "system", "content": SYSTEM_PROMPT}]
    return SESSIONS[sid]

# ----------------------------
# 4. Tool Implementations
# ----------------------------
def search_kb(query):
    query = query.lower()
    
    # BROAD SEARCH LOGIC (Fixing the "only 1 result" issue)
    broad_terms = ["service", "offer", "product", "menu", "list", "available", "what do you do"]
    if any(term in query for term in broad_terms):
        summary = ["Here is an overview of all Kust Bots services:"]
        for key, data in KB["projects"].items():
            summary.append(f"**{data['display_name']}**: {data.get('description', 'See details via specific query.')}")
        return "\n\n".join(summary)

    # SPECIFIC SEARCH LOGIC
    results = []
    for key, data in KB["projects"].items():
        # Check if query matches project key or display name
        if query in key or query in data.get('display_name', '').lower():
            # Return formatted project information
            project_info = f"**{data.get('display_name', 'Unknown Project')}**\n\n"
            project_info += f"{data.get('description', 'No description available.')}\n\n"
            
            if 'features' in data:
                project_info += "**Features:**\n"
                for feature in data['features']:
                    project_info += f"- {feature}\n"
                project_info += "\n"
                
            if 'commands' in data:
                project_info += "**Commands:**\n"
                for command in data['commands']:
                    project_info += f"- {command}\n"
                project_info += "\n"
                
            if 'setup' in data:
                project_info += "**Setup Steps:**\n"
                for step in data['setup']:
                    project_info += f"- {step}\n"
                project_info += "\n"

            if 'subscription' in data:
                project_info += "**Subscription & Renewal:**\n"
                for step in data['subscription']:
                    project_info += f"- {step}\n"
                project_info += "\n"
                
            if 'plans' in data:
                project_info += "**Pricing Plans:**\n"
                for plan, details in data['plans'].items():
                    project_info += f"- **{plan}**: {details}\n"
                project_info += "\n"
                
            results.append(project_info)
    
    # Check for compliance/official channel queries
    if "official" in query or "fake" in query or "real" in query:
        compliance_info = "**Official Kust Bots Information:**\n\n"
        compliance_info += f"Official Channel: {KB['brand']['official_channel']}\n"
        compliance_info += f"Official Support Group: {KB['brand']['official_support_group']}\n"
        compliance_info += f"Owner: {KB['brand']['owner']}\n\n"
        compliance_info += f"{KB['brand']['note']}\n\n"
        compliance_info += f"**Warning:** {KB['compliance']['warn']}\n"
        results.append(compliance_info)
    
    if not results:
        return "No specific record found. Answer based on general Kust knowledge."
    return "\n".join(results[:3])

# ----------------------------
# 5. Core AI Logic (Buffered Streaming)
# ----------------------------
def call_inference_stream(messages):
    payload = {
        "model": INFERENCE_MODEL_ID,
        "messages": messages,
        "stream": True,
        "temperature": 0.5 # Balanced for natural conversation
    }
    
    try:
        with requests.post(API_URL, json=payload, headers=HEADERS, stream=True, timeout=60) as r:
            if r.status_code != 200:
                yield f"data: {json.dumps({'type': 'error', 'content': f'API Error {r.status_code}'})}\n\n"
                return

            # Buffering to hide JSON tool calls
            tool_buffer = ""
            is_collecting_tool = False
            tool_check_buffer = "" 
            check_completed = False

            for line in r.iter_lines():
                if not line: continue
                line = line.decode('utf-8')
                
                if line.startswith('data:'):
                    data_str = line[5:].strip()
                    if data_str == '[DONE]': break
                    
                    try:
                        chunk_json = json.loads(data_str)
                        delta = chunk_json.get('choices', [{}])[0].get('delta', {}).get('content', '')
                        if not delta and 'content' in chunk_json: delta = chunk_json['content']

                        if delta:
                            if not check_completed:
                                tool_check_buffer += delta
                                stripped = tool_check_buffer.strip()
                                # Check if response starts with JSON object
                                if stripped:
                                    if stripped.startswith("{"):
                                        is_collecting_tool = True
                                        tool_buffer = tool_check_buffer
                                    else:
                                        is_collecting_tool = False
                                        yield f"data: {json.dumps({'type': 'token', 'content': tool_check_buffer})}\n\n"
                                    check_completed = True
                                elif len(tool_check_buffer) > 50:
                                    is_collecting_tool = False
                                    yield f"data: {json.dumps({'type': 'token', 'content': tool_check_buffer})}\n\n"
                                    check_completed = True
                            else:
                                if is_collecting_tool:
                                    tool_buffer += delta
                                else:
                                    yield f"data: {json.dumps({'type': 'token', 'content': delta})}\n\n"
                                
                    except: pass

            if is_collecting_tool:
                try:
                    tool_data = json.loads(tool_buffer)
                    tool_name = tool_data.get("tool")
                    query = tool_data.get("query")
                    
                    # 1. Start Tool (Frontend Animation)
                    yield f"data: {json.dumps({'type': 'tool_start', 'tool': tool_name, 'input': query})}\n\n"
                    
                    # 2. Execute
                    time.sleep(0.5)
                    if tool_name == "get_info":
                        tool_result = search_kb(query)
                    else:
                        tool_result = "Tool not found."
                    
                    # 3. End Tool (Frontend Delete Animation)
                    yield f"data: {json.dumps({'type': 'tool_end', 'result': 'Done'})}\n\n"

                    # 4. Recursion with results
                    new_messages = messages + [
                        {"role": "assistant", "content": tool_buffer},
                        {"role": "user", "content": f"TOOL RESULT: {tool_result}"}
                    ]
                    yield from call_inference_stream(new_messages)
                    
                except json.JSONDecodeError:
                    yield f"data: {json.dumps({'type': 'token', 'content': tool_buffer})}\n\n"

    except Exception as e:
        logger.exception(f"Stream Error: {e}")
        yield f"data: {json.dumps({'type': 'error', 'content': 'Connection interrupted.'})}\n\n"

# ----------------------------
# 6. Routes
# ----------------------------
@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/chat/stream", methods=["POST"])
def chat_stream():
    data = request.json
    user_msg = data.get("message")
    sid = data.get("session_id", str(uuid.uuid4()))
    
    if not user_msg: return jsonify({"error": "No message"}), 400

    history = get_session(sid)
    history.append({"role": "user", "content": user_msg})

    # CONTEXT COMPRESSION / SUMMARIZATION LOGIC
    # We keep the System Prompt [0] and the last 8 messages.
    # This effectively "summarizes" the relevant conversation history for every new request.
    if len(history) > 9:
        history = [history[0]] + history[-8:]
        logger.info(f"Session {sid[:8]} context optimized.")

    def generate():
        yield f"data: {json.dumps({'type': 'ping'})}\n\n"
        full_text = ""
        for event in call_inference_stream(history):
            if event.startswith("data: "):
                try:
                    d = json.loads(event[6:])
                    if d['type'] == 'token': full_text += d['content']
                except: pass
            yield event
        
        if full_text and not full_text.strip().startswith("{"):
            history.append({"role": "assistant", "content": full_text})
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

@app.route("/api/reset", methods=["POST"])
def reset():
    sid = request.json.get("session_id")
    if sid in SESSIONS: del SESSIONS[sid]
    return jsonify({"status": "cleared", "new_id": str(uuid.uuid4())})

# ----------------------------
# 7. Frontend
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
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.substring(6));
                            if (data.type === 'tool_start') {
                                activeToolEl = createToolCard(data.input || data.tool);
                            }
                            if (data.type === 'tool_end') {
                                if(activeToolEl) activeToolEl.remove();
                            }
                            if (data.type === 'token') {
                                if (isFirstToken) { botBubble.innerHTML = ''; isFirstToken = false; }
                                currentText += data.content; botBubble.innerHTML = marked.parse(currentText); scrollToBottom();
                            }
                            if (data.type === 'error') botBubble.innerHTML = `<span style="color:#ef4444">Error: ${data.content}</span>`;
                        } catch (e) {}
                    }
                }
            }
        } catch (err) { botBubble.innerHTML = "Connection failed."; } finally { setBusy(false); }
    }
    function ask(q) { inputEl.value = q; sendMessage(); }
    async function resetSession() { if(confirm("Clear chat?")) { await fetch('/api/reset', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({session_id})}); location.reload(); } }
    inputEl.addEventListener('keypress', (e) => { if (e.key === 'Enter') sendMessage(); });
</script>
</body>
</html>
"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"Server starting on port {port}")
    app.run(host="0.0.0.0", port=port, threaded=True)
