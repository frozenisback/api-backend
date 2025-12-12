# main.py
# KUST BOTS OFFICIAL SUPPORT SYSTEM (Production Release - Debug Enabled)
# Single-File Flask Application with Server-Sent Events (SSE) Streaming
# Features: Real-time Typing, Tool Execution Visuals, Premium UI, Auto-Healing Sessions.

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
# Configure logging to flush immediately to stdout (crucial for Heroku)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] KUST: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout
)
logger = logging.getLogger("kust-support")

# Load Environment Variables
INFERENCE_KEY = os.getenv("INFERENCE_KEY", "")
INFERENCE_MODEL_ID = os.getenv("INFERENCE_MODEL_ID", "")
BASE_URL = os.getenv("INFERENCE_URL", "")

# Validate Critical Config
if not (INFERENCE_KEY and INFERENCE_MODEL_ID and BASE_URL):
    logger.error("⚠️ CRITICAL: Missing INFERENCE env vars. Bot will not reply correctly.")

# Ensure URL is correctly formatted
API_URL = f"{BASE_URL.rstrip('/')}/v1/chat/completions"
HEADERS = {
    "Authorization": f"Bearer {INFERENCE_KEY}",
    "Content-Type": "application/json"
}

logger.info(f"System Initialized. Target API: {API_URL}")
logger.info(f"Target Model: {INFERENCE_MODEL_ID}")

# ----------------------------
# 2. Knowledge Base (Business Logic)
# ----------------------------
# Extracted from "SYSTEM ROLE and info about my business.txt"
KB = {
    "projects": {
        "stake_chat_farmer": {
            "name": "Stake Chat Farmer",
            "summary": "Autonomous human-like chat generator for farming XP/Levels.",
            "features": [
                "Per-user memory & mood adaptation",
                "Anti-spam human-flow simulation",
                "Works on all Stake country servers",
                "24/7 operation with Multi-account support"
            ],
            "access": "Bot: @kustchatbot",
            "pricing": "Free 3-hour trial available.",
            "notes": "Not a spam bot. Simulates real human conversation patterns."
        },
        "stake_code_claimer": {
            "name": "Stake Code Claimer",
            "summary": "Automated system to monitor channels and claim codes instantly.",
            "features": [
                "Monitors Stake TG channels",
                "Detects codes instantly",
                "Auto-redeems across accounts",
                "24/7 execution"
            ],
            "notes": "Maximize code capture speed & conversion."
        },
        "frozen_music": {
            "name": "Frozen Music Bot",
            "summary": "Main VC Music Bot (High Performance).",
            "commands": {
                "/play": "Play audio (YouTube/Spotify/Resso/Apple/SC)",
                "/vplay": "Play video + audio",
                "/skip": "Skip track",
                "/couple": "Picks random pair daily",
                "/tmute": "Temp mute user (Admin)"
            },
            "notes": "Distributed backend, caching, multi-node infra."
        },
        "kustify_hosting": {
            "name": "Kustify Hosting",
            "summary": "Bot Hosting Service via @kustifybot.",
            "plans": {
                "Ember": "$1.44/mo (0.25 CPU, 512MB RAM)",
                "Flare": "$2.16/mo (0.5 CPU, 1GB RAM)",
                "Inferno": "$3.60/mo (1 CPU, 2GB RAM)"
            },
            "notes": "Stopped bots cost 2 sparks/day for standby. Deploy via /host."
        },
        "custom_bots": {
            "name": "Paid Custom Bots",
            "summary": "White-label solutions for communities.",
            "pricing": {
                "Commands": "$2–$5 each",
                "Music Tier 1": "$4/mo + $6 setup (4-5 VCs)",
                "Music Tier 2": "$8/mo + $10 setup (~15 VCs)",
                "Music Tier 3": "$20/mo + $25 setup (~50 VCs)"
            }
        }
    },
    "compliance": {
        "official_channels": ["@kustbots", "@kustbotschat", "@KustDev"],
        "rules": [
            "Never mention bonuses, drops, or gambling promotions.",
            "Never start convo with mods.",
            "Never push sales aggressively.",
            "Only official channels are safe."
        ]
    }
}

SYSTEM_PROMPT = f"""
You are the OFFICIAL Support Agent for Kust Bots.
Your Owner: @KustDev. Official Channel: @kustbots.

**CORE RULES:**
1. Direct & Engineering-First: Be concise, professional, no fluff.
2. Safety: WARN users if they mention unofficial channels. ONLY @kustbots is real.
3. Compliance: NEVER discuss gambling bonuses, drops, or predictions.
4. Sales: Explain pricing clearly (Ember $1.44, Flare $2.16, Inferno $3.60) but do not "push" sales.

**TOOL USAGE:**
You have access to a live database. If a user asks for specific prices, commands, or project details, you MUST use the `get_info` tool.
To use a tool, your response must be ONLY a JSON object:
{{"tool": "get_info", "query": "kustify pricing"}}

**RESPONSE STYLE:**
- Use Markdown.
- If listing steps, use numbers.
- If listing commands, use code blocks `like this`.
- Be helpful but concise.
"""

# ----------------------------
# 3. Flask App & Session Management
# ----------------------------
app = Flask(__name__)
# In-memory storage for active chat sessions
# Structure: { session_id: [ {role, content}, ... ] }
SESSIONS = {}

def get_session(sid):
    if sid not in SESSIONS:
        SESSIONS[sid] = [{"role": "system", "content": SYSTEM_PROMPT}]
    return SESSIONS[sid]

# ----------------------------
# 4. Tool Implementations
# ----------------------------
def search_kb(query):
    """Fuzzy searches the KB for relevant info."""
    query = query.lower()
    results = []
    
    # Check Projects
    for key, data in KB["projects"].items():
        blob = str(data).lower()
        if query in key or query in data['name'].lower() or any(w in blob for w in query.split()):
            results.append(f"Project: {data['name']}\nData: {json.dumps(data, indent=2)}")
    
    # Check Compliance/General
    if "official" in query or "fake" in query or "channel" in query:
        results.append(f"Official Channels: {KB['compliance']['official_channels']}")
    
    if not results:
        return "No specific database record found. Answer based on general knowledge."
    return "\n\n".join(results[:3]) # Return top 3 matches

# ----------------------------
# 5. Core AI Logic (Streaming)
# ----------------------------
def call_inference_stream(messages):
    """
    Generator that streams chunks from the LLM.
    If the LLM returns a Tool Call (JSON), we handle it and yield events.
    """
    payload = {
        "model": INFERENCE_MODEL_ID,
        "messages": messages,
        "stream": True,  # Enable streaming from upstream
        "temperature": 0.5
    }
    
    logger.info(f"Initiating Inference Call to {API_URL}")
    
    try:
        # 1. Start Request
        with requests.post(API_URL, json=payload, headers=HEADERS, stream=True, timeout=60) as r:
            logger.info(f"Inference API Response: {r.status_code}")
            
            if r.status_code != 200:
                error_msg = r.text
                logger.error(f"Upstream API Error: {r.status_code} - {error_msg}")
                yield f"data: {json.dumps({'type': 'error', 'content': f'API Error {r.status_code}: {error_msg}'})}\n\n"
                return

            full_content = ""
            chunk_count = 0
            
            # 2. Process Stream
            for line in r.iter_lines():
                if not line: continue
                line = line.decode('utf-8')
                
                # Debug logging for the first few lines to verify format
                if chunk_count < 3:
                    logger.info(f"Raw Stream Line: {line}")
                
                if line.startswith('data: '):
                    data_str = line[6:]
                    if data_str.strip() == '[DONE]':
                        logger.info("Stream received [DONE] signal.")
                        break
                    try:
                        chunk_json = json.loads(data_str)
                        
                        # Handle standard OpenAI format
                        delta = chunk_json.get('choices', [{}])[0].get('delta', {}).get('content', '')
                        
                        # Handle potential alternative format (some providers differ)
                        if not delta and 'content' in chunk_json:
                            delta = chunk_json['content']

                        if delta:
                            chunk_count += 1
                            full_content += delta
                            # Yield token to frontend
                            yield f"data: {json.dumps({'type': 'token', 'content': delta})}\n\n"
                    except Exception as e:
                        logger.warning(f"Failed to parse chunk: {data_str} | Error: {e}")
            
            if chunk_count == 0:
                logger.warning("Stream finished but NO tokens were parsed. Check API response format.")
            
            # 3. Check for Tool Use in the accumulated content
            stripped = full_content.strip()
            # Heuristic: If content looks like a JSON tool call
            if stripped.startswith('{') and '"tool"' in stripped and stripped.endswith('}'):
                try:
                    tool_data = json.loads(stripped)
                    tool_name = tool_data.get("tool")
                    query = tool_data.get("query")
                    
                    logger.info(f"Tool Triggered: {tool_name} with query: {query}")
                    
                    # Notify Frontend: Tool Started
                    yield f"data: {json.dumps({'type': 'tool_start', 'tool': tool_name, 'input': query})}\n\n"
                    
                    # Execute Tool
                    time.sleep(0.8) # Artificial delay for "Animation" feel
                    if tool_name == "get_info":
                        tool_result = search_kb(query)
                    else:
                        tool_result = "Tool not found."
                    
                    logger.info(f"Tool Result: {tool_result[:50]}...")
                    
                    # Notify Frontend: Tool Done
                    yield f"data: {json.dumps({'type': 'tool_end', 'result': 'Data retrieved.'})}\n\n"
                    
                    # 4. Recursion: Call LLM again with tool result
                    new_messages = messages + [
                        {"role": "assistant", "content": stripped},
                        {"role": "user", "content": f"TOOL RESULT: {tool_result}"}
                    ]
                    
                    # Stream the final answer (recursive yield from new generator)
                    yield from call_inference_stream(new_messages)
                    
                except json.JSONDecodeError:
                    # Not valid JSON, just treat as text
                    logger.info("Response looked like JSON but failed decode, treating as text.")
                    pass

    except Exception as e:
        logger.exception(f"Stream Exception: {e}")
        yield f"data: {json.dumps({'type': 'error', 'content': 'Internal Connection Error.'})}\n\n"

# ----------------------------
# 6. Routes
# ----------------------------

@app.route("/")
def index():
    logger.info(f"Page Load - IP: {request.remote_addr}")
    return render_template_string(HTML_TEMPLATE)

@app.route("/chat/stream", methods=["POST"])
def chat_stream():
    data = request.json
    user_msg = data.get("message")
    sid = data.get("session_id", str(uuid.uuid4()))
    
    logger.info(f"Session {sid[:8]} - User Msg: {user_msg}")
    
    if not user_msg:
        return jsonify({"error": "No message"}), 400

    # Update History
    history = get_session(sid)
    history.append({"role": "user", "content": user_msg})

    def generate():
        # Yield a ping to confirm connection immediately
        yield f"data: {json.dumps({'type': 'ping'})}\n\n"
        
        full_response_accumulator = ""
        
        # Stream response
        for event in call_inference_stream(history):
            # Capture content to save to history later
            if event.startswith("data: "):
                try:
                    evt_data = json.loads(event[6:])
                    if evt_data['type'] == 'token':
                        full_response_accumulator += evt_data['content']
                except: pass
            yield event
            
        # Save Assistant Response to Memory
        if full_response_accumulator and not full_response_accumulator.strip().startswith("{"):
            history.append({"role": "assistant", "content": full_response_accumulator})
        
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return Response(
        stream_with_context(generate()), 
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive'
        }
    )

@app.route("/api/reset", methods=["POST"])
def reset():
    sid = request.json.get("session_id")
    if sid in SESSIONS:
        del SESSIONS[sid]
        logger.info(f"Session {sid[:8]} cleared.")
    return jsonify({"status": "cleared", "new_id": str(uuid.uuid4())})

# ----------------------------
# 7. Frontend Template (HTML/CSS/JS)
# ----------------------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>KUST BOTS | Support Terminal</title>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Inter:wght@300;400;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #050505;
            --panel: #0f0f13;
            --border: #27272a;
            --primary: #3b82f6; /* Blue */
            --accent: #8b5cf6; /* Purple */
            --text: #e4e4e7;
            --text-dim: #a1a1aa;
            --tool-bg: #1e1e24;
            --success: #10b981;
        }
        
        * { box-sizing: border-box; }
        body { 
            margin: 0; padding: 0; 
            background-color: var(--bg); 
            color: var(--text); 
            font-family: 'Inter', sans-serif; 
            height: 100vh; 
            display: flex; 
            overflow: hidden;
        }

        /* --- Sidebar --- */
        .sidebar {
            width: 300px;
            background: var(--panel);
            border-right: 1px solid var(--border);
            padding: 24px;
            display: flex;
            flex-direction: column;
            gap: 20px;
            display: none; /* Hidden on mobile by default */
        }
        @media(min-width: 768px) { .sidebar { display: flex; } }

        .brand { 
            font-family: 'JetBrains Mono', monospace; 
            font-weight: 700; 
            font-size: 1.2rem; 
            color: #fff; 
            letter-spacing: -1px;
            display: flex; align-items: center; gap: 10px;
        }
        .brand span { color: var(--primary); }

        .status-box {
            padding: 12px;
            background: rgba(255,255,255,0.03);
            border-radius: 8px;
            border: 1px solid var(--border);
            font-size: 0.85rem;
        }
        .status-indicator {
            display: inline-block; width: 8px; height: 8px; 
            border-radius: 50%; background: var(--text-dim);
            margin-right: 8px;
        }
        .status-indicator.live { background: var(--success); box-shadow: 0 0 10px var(--success); }
        .status-indicator.busy { background: var(--accent); animation: pulse 1s infinite; }

        .quick-actions { display: flex; flex-direction: column; gap: 8px; }
        .action-btn {
            background: transparent;
            border: 1px solid var(--border);
            color: var(--text-dim);
            padding: 10px;
            border-radius: 6px;
            cursor: pointer;
            text-align: left;
            transition: all 0.2s;
            font-size: 0.9rem;
        }
        .action-btn:hover { border-color: var(--primary); color: #fff; background: rgba(59,130,246,0.1); }

        /* --- Main Chat --- */
        .main { flex: 1; display: flex; flex-direction: column; position: relative; }
        
        .chat-container {
            flex: 1;
            padding: 20px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 20px;
            scroll-behavior: smooth;
        }

        /* Message Bubbles */
        .message {
            max-width: 800px;
            margin: 0 auto;
            width: 100%;
            display: flex;
            gap: 16px;
            opacity: 0;
            animation: fadeIn 0.3s forwards;
        }
        .message.user { justify-content: flex-end; }
        
        .avatar {
            width: 36px; height: 36px;
            border-radius: 8px;
            background: var(--panel);
            border: 1px solid var(--border);
            display: flex; align-items: center; justify-content: center;
            font-size: 1.2rem;
            flex-shrink: 0;
        }
        .message.user .avatar { order: 2; background: var(--primary); border-color: var(--primary); color: white; }
        
        .bubble {
            background: var(--panel);
            border: 1px solid var(--border);
            padding: 12px 18px;
            border-radius: 12px;
            font-size: 0.95rem;
            line-height: 1.6;
            position: relative;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }
        .message.user .bubble {
            background: var(--primary);
            color: white;
            border-color: var(--primary);
            text-align: right;
        }

        /* Tool Animation Card */
        .tool-card {
            max-width: 800px;
            margin: 0 auto;
            background: var(--tool-bg);
            border: 1px solid var(--accent);
            border-left: 4px solid var(--accent);
            padding: 10px 16px;
            border-radius: 6px;
            color: #d8b4fe;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85rem;
            display: flex;
            align-items: center;
            gap: 12px;
            animation: slideIn 0.4s ease-out;
            margin-bottom: -10px; /* Pull closer to next msg */
        }
        .tool-spinner {
            width: 14px; height: 14px;
            border: 2px solid rgba(139, 92, 246, 0.3);
            border-top-color: var(--accent);
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        
        /* Markdown Styles within Bubbles */
        .bubble p { margin: 0 0 10px 0; }
        .bubble p:last-child { margin: 0; }
        .bubble code { background: rgba(0,0,0,0.3); padding: 2px 5px; border-radius: 4px; font-family: 'JetBrains Mono', monospace; font-size: 0.9em; }
        .bubble pre { background: #000; padding: 10px; border-radius: 8px; overflow-x: auto; }
        .bubble ul { padding-left: 20px; }

        /* Input Area */
        .input-area {
            padding: 20px;
            background: rgba(5,5,5,0.9);
            border-top: 1px solid var(--border);
            backdrop-filter: blur(10px);
        }
        .input-wrapper {
            max-width: 800px;
            margin: 0 auto;
            position: relative;
            display: flex;
            gap: 10px;
        }
        input {
            width: 100%;
            background: var(--panel);
            border: 1px solid var(--border);
            padding: 14px 18px;
            border-radius: 10px;
            color: white;
            font-family: inherit;
            font-size: 1rem;
            outline: none;
            transition: border-color 0.2s;
        }
        input:focus { border-color: var(--primary); }
        button.send {
            background: var(--primary);
            color: white;
            border: none;
            padding: 0 24px;
            border-radius: 10px;
            font-weight: 600;
            cursor: pointer;
            transition: opacity 0.2s;
        }
        button.send:disabled { opacity: 0.5; cursor: not-allowed; }

        /* Animations */
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes slideIn { from { opacity: 0; transform: translateX(-20px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.4; } 100% { opacity: 1; } }

        /* Thinking Dots */
        .thinking { display: flex; gap: 4px; padding: 4px; }
        .dot { width: 6px; height: 6px; background: var(--text-dim); border-radius: 50%; animation: bounce 1.4s infinite ease-in-out both; }
        .dot:nth-child(1) { animation-delay: -0.32s; }
        .dot:nth-child(2) { animation-delay: -0.16s; }
        @keyframes bounce { 0%, 80%, 100% { transform: scale(0); } 40% { transform: scale(1); } }

    </style>
</head>
<body>

    <!-- Sidebar -->
    <div class="sidebar">
        <div class="brand">
            <span>//</span> KUST BOTS
        </div>
        <div class="status-box">
            <div id="status-dot" class="status-indicator live"></div>
            <span id="status-text">System Online</span>
        </div>
        
        <div class="quick-actions">
            <div style="font-size:0.75rem; color:var(--text-dim); text-transform:uppercase; letter-spacing:1px; margin-bottom:4px;">Quick Access</div>
            <button class="action-btn" onclick="ask('What is Kustify Hosting pricing?')">💰 Hosting Plans</button>
            <button class="action-btn" onclick="ask('How do I setup the Stake Chat Farmer?')">🤖 Stake Farmer Setup</button>
            <button class="action-btn" onclick="ask('Show me commands for Frozen Music Bot')">🎵 Music Bot Cmds</button>
            <button class="action-btn" onclick="ask('Verify if @kustsupport is real')">⚠️ Verify Channel</button>
        </div>

        <div style="margin-top:auto; font-size:0.75rem; color:var(--text-dim);">
            Session ID: <span id="sess-id" style="font-family:monospace">...</span><br>
            <a href="#" onclick="resetSession()" style="color:var(--accent)">Reset Session</a>
        </div>
    </div>

    <!-- Main -->
    <div class="main">
        <div class="chat-container" id="chat">
            <!-- Welcome Message -->
            <div class="message">
                <div class="avatar">🤖</div>
                <div class="bubble">
                    <p><strong>Connected to Kust Support Core.</strong></p>
                    <p>I can help with Kustify, Music Bots, Stake Tools, and Billing. How can I assist you today?</p>
                </div>
            </div>
        </div>

        <div class="input-area">
            <div class="input-wrapper">
                <input type="text" id="userInput" placeholder="Type your issue or command..." autocomplete="off">
                <button class="send" id="sendBtn" onclick="sendMessage()">SEND</button>
            </div>
        </div>
    </div>

<script>
    // Utils
    const uuid = () => Math.random().toString(36).substring(2) + Date.now().toString(36);
    let session_id = localStorage.getItem('kust_sid') || uuid();
    localStorage.setItem('kust_sid', session_id);
    document.getElementById('sess-id').innerText = session_id.substring(0,8);

    const chatEl = document.getElementById('chat');
    const inputEl = document.getElementById('userInput');
    const sendBtn = document.getElementById('sendBtn');
    const statusDot = document.getElementById('status-dot');
    const statusText = document.getElementById('status-text');

    function setBusy(busy) {
        if(busy) {
            statusDot.className = 'status-indicator busy';
            statusText.innerText = 'Processing...';
            sendBtn.disabled = true;
            inputEl.disabled = true;
        } else {
            statusDot.className = 'status-indicator live';
            statusText.innerText = 'System Online';
            sendBtn.disabled = false;
            inputEl.disabled = false;
            inputEl.focus();
        }
    }

    function appendUserMsg(text) {
        const div = document.createElement('div');
        div.className = 'message user';
        div.innerHTML = `<div class="bubble">${text}</div><div class="avatar">👤</div>`;
        chatEl.appendChild(div);
        scrollToBottom();
    }

    function createBotMsg() {
        const div = document.createElement('div');
        div.className = 'message';
        div.innerHTML = `
            <div class="avatar">🤖</div>
            <div class="bubble">
                <div class="thinking">
                    <div class="dot"></div><div class="dot"></div><div class="dot"></div>
                </div>
            </div>`;
        chatEl.appendChild(div);
        scrollToBottom();
        return div.querySelector('.bubble');
    }

    function createToolCard(toolName) {
        const div = document.createElement('div');
        div.className = 'tool-card';
        div.innerHTML = `<div class="tool-spinner"></div> <span>Executing: ${toolName}...</span>`;
        // Insert before the last message (which is usually the bot typing)
        chatEl.insertBefore(div, chatEl.lastElementChild);
        scrollToBottom();
        return div;
    }

    function scrollToBottom() {
        chatEl.scrollTop = chatEl.scrollHeight;
    }

    async function sendMessage() {
        const text = inputEl.value.trim();
        if(!text) return;
        
        inputEl.value = '';
        appendUserMsg(text);
        setBusy(true);

        const botBubble = createBotMsg(); // Create placeholder with dots
        let currentText = "";
        let isFirstToken = true;

        try {
            const response = await fetch('/chat/stream', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ message: text, session_id: session_id })
            });

            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                
                const chunk = decoder.decode(value);
                const lines = chunk.split('\\n\\n'); // Split SSE events
                
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.substring(6));
                            
                            if (data.type === 'ping') continue;
                            
                            if (data.type === 'tool_start') {
                                createToolCard(data.input || data.tool);
                            }
                            
                            if (data.type === 'token') {
                                if (isFirstToken) {
                                    botBubble.innerHTML = ''; // Remove thinking dots
                                    isFirstToken = false;
                                }
                                currentText += data.content;
                                botBubble.innerHTML = marked.parse(currentText);
                                scrollToBottom();
                            }
                            
                            if (data.type === 'error') {
                                botBubble.innerHTML = `<span style="color:#ef4444">Error: ${data.content}</span>`;
                            }

                        } catch (e) {
                            console.log("Parse error", e);
                        }
                    }
                }
            }
        } catch (err) {
            botBubble.innerHTML = "Connection failed. Please reset.";
        } finally {
            setBusy(false);
        }
    }

    function ask(q) {
        inputEl.value = q;
        sendMessage();
    }

    async function resetSession() {
        if(confirm("Clear chat history?")) {
            await fetch('/api/reset', {
                method:'POST', 
                headers:{'Content-Type':'application/json'},
                body: JSON.stringify({session_id})
            });
            location.reload();
        }
    }

    // Enter key support
    inputEl.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });

</script>
</body>
</html>
"""

if __name__ == "__main__":
    # Heroku/Production Entry Point
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"Server starting on port {port}")
    app.run(host="0.0.0.0", port=port, threaded=True)
