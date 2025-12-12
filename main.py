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
    "kb_version": "2025-12-12",
    "brand": {
        "name": "Kust Bots",
        "owner": "@KustDev",
        "official_channel": "@kustbots",
        "official_support_group": "@kustbotschat",
        "notes": "All other accounts/channels claiming to be Kust Bots are fake."
    },
    "contact": {
        "support_bot": "@kustifybot",
        "sales_contact": "@KustXoffical",
        "urgent_escalation": "@KustDev"
    },
    "products": {
        "stake_chat_farmer": {
            "display_name": "AI Stake Chat Farmer",
            "description": "Human-like autonomous chat emulator for Stake servers. Per-user memory, mood adaptation, human delay simulation, multi-account scaling.",
            "access": "@kustchatbot",
            "features": [
                "Per-user memory & topic tracking",
                "Mood adaptation & tone shifting",
                "Context-aware replies with mention handling",
                "Smart timing & human delay simulation",
                "Per-chat awareness (avoids repeating spam)",
                "Multi-account farming at scale",
                "24/7 autonomous operation",
                "Free 3-hour trial"
            ],
            "use_cases": [
                "Increase chat activity levels",
                "Emulate real user interactions",
                "Automated conversation seeding for engagement metrics"
            ],
            "security_considerations": [
                "Respect platform ToS — customer warned about liability",
                "Rate-limit accounts per-provider to avoid bans",
                "Rotate proxies and sessions per-account",
                "Audit logs kept for every session"
            ],
            "support_tips": [
                "Ask: 'Which server/country and how many accounts?'",
                "Collect: trial token, desired tone profile, schedule windows",
                "Common fixes: adjust human delay window; reset per-user memory"
            ]
        },
        "stake_code_claimer": {
            "display_name": "Stake Code Claimer",
            "description": "Monitors Stake Telegram channels for promo codes and auto-redeems across configured accounts.",
            "features": [
                "Channel scraping + realtime code detection",
                "Instant multi-account redemption",
                "Fast webhook or push-notify pipeline",
                "Blacklist/whitelist for channels"
            ],
            "support_tips": [
                "Ask: 'Provide channel links and account list (IDs).' ",
                "Verify: bot has read permissions in monitored channels",
                "Common fixes: fix parser regex; increase scrape frequency; add fallback redeem endpoints"
            ],
            "security_considerations": [
                "Rotate redemption endpoints to avoid rate blocks",
                "Store secrets encrypted",
                "Alert on failed redemptions"
            ]
        },
        "frozen_music_bot": {
            "display_name": "Frozen Music (VC Music Bot)",
            "description": "Main voice-chat (VC) music bot with multi-source streaming and a distributed playback backend.",
            "core_commands": {
                "music": [
                    "/play <song name or URL> - plays song from YT/Spotify/Resso/Apple/SoundCloud or replied media",
                    "/vplay <url | query> - plays video + audio",
                    "/playlist - view/manage playlists",
                    "/skip - skip current (admin only)",
                    "/pause - pause stream (admin only)",
                    "/resume - resume (admin only)",
                    "/stop or /end - stop and clear queue (admin only)"
                ],
                "admin": [
                    "/mute @user",
                    "/unmute @user",
                    "/tmute @user <minutes>",
                    "/kick @user",
                    "/ban @user",
                    "/unban @user"
                ],
                "utility": [
                    "/ping - response time & uptime",
                    "/clear - clear queue (admin only)",
                    "/couple - daily cached random pair (per-group cache)"
                ]
            },
            "backend": {
                "architecture": "distributed nodes with metadata server, distribution server, playback nodes, download servers (yt-dlp fallback), multi-layer caching",
                "limits": {
                    "max_stream_duration_seconds": 7800,
                    "auto_fallback_for_long_tracks": True
                }
            },
            "support_tips": [
                "Ask for: bot username, chat id, exact command used, timestamp, logs or traceback if present",
                "Common fixes: restart playback node, clear queue, re-cache thumbnail/metadata, validate CDN audio URL"
            ]
        },
        "kustify_hosting": {
            "display_name": "Kustify Hosting (Bot Hosting Service)",
            "bot": "@kustifybot",
            "description": "Lightweight bot hosting with instant deployment and minimal pricing.",
            "commands": [
                "/host - create instance",
                "/mybots - list/manage instances",
                "/balance - check Sparks balance",
                "/buysparks - purchase Sparks",
                "/logs - fetch build/runtime logs",
                "/env - update environment variables",
                "/restart - restart instance",
                "/stop - stop instance",
                "/resume - resume instance",
                "/delete - delete instance"
            ],
            "pricing": {
                "ember": { "cpu": 0.25, "ram_mb": 512, "price_usd_per_month": 1.44 },
                "flare": { "cpu": 0.5, "ram_mb": 1024, "price_usd_per_month": 2.16 },
                "inferno": { "cpu": 1, "ram_mb": 2048, "price_usd_per_month": 3.60 },
                "standby_cost_sparks_per_day": 2
            },
            "support_tips": [
                "Ask for: instance id, last deploy log, requested plan",
                "Common fixes: check build log, increase RAM if OOM, rotate API keys in env"
            ],
            "security": [
                "Do not expose admin ports publicly",
                "Provide env-edit via secure vault",
                "Auto-restore on crash enabled"
            ]
        },
        "paid_custom_bots": {
            "description": "Custom bot development service; per-command pricing and monthly hosting options.",
            "pricing_guidelines": {
                "per_command": "2-5 USD depending on complexity",
                "music_bot_plans": [
                    { "monthly": 4, "setup": 6, "vcs": "4-5" },
                    { "monthly": 8, "setup": 10, "vcs": "approx 15" },
                    { "monthly": 20, "setup": 25, "vcs": "approx 50" }
                ]
            },
            "support_tips": [
                "Collect: requirements spec, target chat size, admin list, 3rd-party API keys",
                "Deliver: staging bot, test plan, handover doc"
            ]
        }
    },
    "support_rules": {
        "official_only": {
            "channels": ["@kustbots", "@kustbotschat", "@KustDev"],
            "instruction": "Always verify against the official channel before giving instructions or accepting payments."
        },
        "interaction": {
            "tone": "professional, concise, direct",
            "max_simultaneous_users": 2,
            "escalation_on_more_than_two": "Respond only to first two; advise others to wait or post in support group."
        },
        "prohibited": [
            "Never mention bonuses, drops, weekly or monthly gambling promotions",
            "Never initiate conversations with moderators (only reply if they initiate)",
            "Never promote or arrange off-platform financial transactions in chat",
            "Never acknowledge or recommend fake accounts or clones"
        ]
    },
    "troubleshooting": {
        "general_steps": [
            "1) Reproduce the issue and collect exact command and timestamp.",
            "2) Request bot username, chat id, and logs (if available).",
            "3) Check node health and queue status.",
            "4) Clear cache or restart affected node.",
            "5) If unresolved, escalate with logs and replication steps."
        ],
        "music_playback_issues": {
            "symptoms": ["no audio", "stuttering", "queue not progressing"],
            "quick_fixes": [
                "Verify direct CDN audio URL",
                "Restart playback node for that chat",
                "Check if the download server returned a valid stream",
                "Ensure yt-dlp fallback is functioning"
            ]
        },
        "hosting_issues": {
            "symptoms": ["failed build", "OOM", "instance won't start"],
            "quick_fixes": [
                "Inspect build logs for missing dependency",
                "Increase RAM/CPU plan if OOM",
                "Redeploy with cleared cache",
                "Rotate secret environment variables if auth fails"
            ]
        },
        "stake_tools_issues": {
            "symptoms": ["redeem fails", "bot blocked", "triggers anti-bot"],
            "quick_fixes": [
                "Rotate proxy/session",
                "Lower automation frequency or add jitter",
                "Check parser regex for new code formats",
                "Re-auth accounts and verify two-factor if present"
            ]
        }
    },
    "onboarding": {
        "support_agent_checklist": [
            "Know official channels and contact handles",
            "Verify product ownership before any transaction",
            "Confirm user identity if requesting sensitive actions",
            "Collect necessary logs/screenshots before troubleshooting",
            "Follow compliance & prohibited list strictly"
        ],
        "trial_activation_steps_for_stake_chat_farmer": [
            "1) Validate trial slot availability",
            "2) Request target server and sample conversation tone profile",
            "3) Provision trial accounts (ephemeral) and start 3-hour session",
            "4) Monitor and capture engagement metrics, provide summary to user"
        ],
        "provisioning_hosting_instance": [
            "1) Get requested plan and bot repo link",
            "2) Create instance and return instance id",
            "3) Provide env var template and guide for secrets",
            "4) Share logs & access instructions"
        ]
    }
}

SYSTEM_PROMPT = """
You are KustX, the official AI support for Kust Bots.

**IDENTITY:**
- Name: KustX
- Owner: @KustDev
- Official Channel: @kustbots
- Support Group: @kustbotschat

**BEHAVIOR:**
1. **Professional & Direct:** Use a professional, concise, and direct tone. Do not ramble.
2. **Formatting:** IMPORTANT: When listing features, plans, commands, or troubleshooting steps, ALWAYS use Markdown bullet points.
3. **Safety & Compliance:**
   - NEVER mention gambling bonuses, drops, or predictions.
   - WARN users about fake accounts. Only @kustbots and @KustDev are official.
   - Do not promote off-platform financial transactions in chat.
4. **Tool Use:** Use the `get_info` tool to fetch data. Output ONLY JSON for tools.
   - Example: {"tool": "get_info", "query": "pricing"}

**DATA ACCESS:**
- Use `get_info` with queries like "services", "troubleshoot", "rules", or specific product names to retrieve knowledge.
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
    
    # BROAD SEARCH LOGIC
    broad_terms = ["service", "offer", "product", "menu", "list", "available", "what do you do"]
    if any(term in query for term in broad_terms):
        summary = ["Here is an overview of all Kust Bots products:"]
        for key, data in KB["products"].items():
            desc = data.get('description', 'See details via specific query.')
            summary.append(f"**{data.get('display_name', key)}**: {desc}")
        return "\n\n".join(summary)

    # SPECIFIC SEARCH LOGIC
    results = []
    
    # Check Products
    for key, data in KB["products"].items():
        blob = str(data).lower()
        if query in key or query in data.get('display_name', '').lower() or any(w in blob for w in query.split()):
            results.append(f"PRODUCT {data.get('display_name')}: {json.dumps(data)}")
    
    # Check Troubleshooting
    if any(w in query for w in ["error", "fix", "fail", "broken", "issue", "problem", "help", "bug", "stutter"]):
        results.append(f"TROUBLESHOOTING GUIDE: {json.dumps(KB['troubleshooting'])}")

    # Check Compliance/Rules
    if any(w in query for w in ["rule", "ban", "gamble", "fake", "official", "scam", "owner"]):
        results.append(f"OFFICIAL CHANNELS & RULES: {json.dumps(KB['brand'])}\n{json.dumps(KB['support_rules'])}")
    
    if not results:
        return "No specific record found. Answer based on general Kust knowledge or suggest contacting @KustDev for unsupported issues."
    
    return "\n".join(results[:4])

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
                                stripped = tool_check_buffer.lstrip()
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
