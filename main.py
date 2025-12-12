# main.py
# KUST BOTS OFFICIAL SUPPORT SYSTEM (Production Release - V2 KustX)
# Single-File Flask Application with Server-Sent Events (SSE) Streaming
# Features: Backend Buffering (Hides JSON), Real-time Typing, Context Compression, Strict Guardrails.

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

logger.info(f"System Initialized. Model: {INFERENCE_MODEL_ID}")

# ----------------------------
# 2. Knowledge Base (Business Logic)
# ----------------------------
KB = {
    "projects": {
        "stake_chat_farmer": {
            "name": "Stake Chat Farmer",
            "access": "@kustchatbot",
            "price": "Free 3-hour trial",
            "features": "Autonomous chat generator. Not spam. Farms XP/Levels. 24/7. Multi-account.",
            "setup": "Start bot -> Link account -> Set mood -> Start farming."
        },
        "stake_code_claimer": {
            "name": "Stake Code Claimer",
            "info": "Monitors channels, claims codes instantly across accounts. 24/7 execution."
        },
        "frozen_music": {
            "name": "Frozen Music Bot",
            "commands": ["/play", "/vplay", "/skip", "/couple", "/tmute"],
            "info": "High-performance VC music bot. Distributed backend for stability."
        },
        "kustify_hosting": {
            "name": "Kustify Hosting",
            "bot": "@kustifybot",
            "plans": {
                "Ember": "$1.44/mo (0.25 CPU/512MB)",
                "Flare": "$2.16/mo (0.5 CPU/1GB)",
                "Inferno": "$3.60/mo (1 CPU/2GB)"
            },
            "info": "Deploy via /host. Stopped bots cost 2 sparks/day."
        },
        "custom_bots": {
            "name": "Paid Custom Bots",
            "pricing": "Commands: $2-$5. Music Bots: $4/mo (Tier 1) to $20/mo (Tier 3).",
            "info": "White-label solutions."
        }
    },
    "compliance": {
        "official": ["@kustbots", "@kustbotschat", "@KustDev"],
        "warn": "Beware of fakes. We NEVER discuss gambling bonuses, drops, or predictions."
    }
}

SYSTEM_PROMPT = """
You are KustX, the official AI support for Kust Bots.

**IDENTITY:**
- Name: KustX
- Owner: @KustDev
- Official Channel: @kustbots

**BEHAVIOR RULES:**
1. **Concise:** Answers must be very short. Bullet points preferred. No fluff.
2. **First Contact:** If the user says "hi" or "hello", reply ONLY: "Hi, I'm KustX. How can I help?"
3. **Guardrails:** If asked to generate code, write essays, solve math, or discuss general topics/competitors, reply EXACTLY: "I cannot do that. I only support Kust Bots."
4. **Tool Use:** If you need specific data (prices, commands), output ONLY a JSON object. Example: {"tool": "get_info", "query": "pricing"}
5. **No Sales Pressure:** State prices clearly. Do not ask "Would you like to buy?".

**DATA:**
- Use the `get_info` tool for looking up project details.
"""

# ----------------------------
# 3. Flask App & Session Management
# ----------------------------
app = Flask(__name__)
# In-memory storage for active chat sessions
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
    results = []
    
    # Check Projects
    for key, data in KB["projects"].items():
        blob = str(data).lower()
        if query in key or query in data['name'].lower() or any(w in blob for w in query.split()):
            # Return compact JSON for the LLM to read
            results.append(f"{data['name']}: {json.dumps(data)}")
    
    # Check Compliance
    if "official" in query or "fake" in query or "real" in query:
        results.append(str(KB['compliance']))
    
    if not results:
        return "No specific record found. Answer concisely based on general Kust knowledge."
    return "\n".join(results[:2])

# ----------------------------
# 5. Core AI Logic (Buffered Streaming)
# ----------------------------
def call_inference_stream(messages):
    """
    Generator that streams chunks.
    CRITICAL: Buffers content if it looks like JSON to hide it from the user.
    """
    payload = {
        "model": INFERENCE_MODEL_ID,
        "messages": messages,
        "stream": True,
        "temperature": 0.3  # Low temp for strict/concise answers
    }
    
    logger.info("Calling Inference API...")
    
    try:
        with requests.post(API_URL, json=payload, headers=HEADERS, stream=True, timeout=60) as r:
            if r.status_code != 200:
                logger.error(f"API Error: {r.status_code} - {r.text}")
                yield f"data: {json.dumps({'type': 'error', 'content': f'API Error {r.status_code}'})}\n\n"
                return

            # --- BUFFERING LOGIC ---
            tool_buffer = ""
            is_collecting_tool = False
            has_started = False

            for line in r.iter_lines():
                if not line: continue
                line = line.decode('utf-8')
                
                # Handle 'data:' with or without space
                if line.startswith('data:'):
                    data_str = line[5:].strip()
                    if data_str == '[DONE]': break
                    
                    try:
                        chunk_json = json.loads(data_str)
                        delta = chunk_json.get('choices', [{}])[0].get('delta', {}).get('content', '')
                        # Handle alternate format
                        if not delta and 'content' in chunk_json: delta = chunk_json['content']

                        if delta:
                            # Heuristic: If the VERY FIRST content starts with '{', assume it's a tool call and buffer it.
                            if not has_started:
                                if delta.strip().startswith("{"):
                                    is_collecting_tool = True
                                has_started = True
                            
                            if is_collecting_tool:
                                tool_buffer += delta
                            else:
                                # Normal text stream - send immediately to user
                                yield f"data: {json.dumps({'type': 'token', 'content': delta})}\n\n"
                                
                    except Exception as e:
                        pass # Ignore parse errors on partial chunks

            # Stream ended. Check if we have a buffered tool call.
            if is_collecting_tool:
                logger.info(f"Buffered Tool Call: {tool_buffer}")
                # Try to parse as JSON
                try:
                    tool_data = json.loads(tool_buffer)
                    tool_name = tool_data.get("tool")
                    query = tool_data.get("query")
                    
                    # 1. Notify Frontend: Tool Started (Shows Animation)
                    yield f"data: {json.dumps({'type': 'tool_start', 'tool': tool_name, 'input': query})}\n\n"
                    
                    # 2. Execute Tool
                    time.sleep(0.6) # Slight delay for visual effect
                    if tool_name == "get_info":
                        tool_result = search_kb(query)
                    else:
                        tool_result = "Tool not found."
                    
                    logger.info(f"Tool Result: {tool_result[:50]}...")

                    # 3. Recursion: Call LLM again with tool result
                    # We inject the tool output as a User message to prompt the final answer
                    new_messages = messages + [
                        {"role": "assistant", "content": tool_buffer},
                        {"role": "user", "content": f"TOOL RESULT: {tool_result}"}
                    ]
                    
                    # Stream the final answer (recursive)
                    yield from call_inference_stream(new_messages)
                    
                except json.JSONDecodeError:
                    # Failed to parse buffer as JSON? Just stream it as text (fallback)
                    logger.warning("Failed to parse tool buffer as JSON. Streaming as text.")
                    yield f"data: {json.dumps({'type': 'token', 'content': tool_buffer})}\n\n"

    except Exception as e:
        logger.exception(f"Stream Exception: {e}")
        yield f"data: {json.dumps({'type': 'error', 'content': 'Connection interrupted.'})}\n\n"

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
    
    if not user_msg:
        return jsonify({"error": "No message"}), 400

    logger.info(f"Session {sid[:8]} User: {user_msg}")

    # Get History
    history = get_session(sid)
    history.append({"role": "user", "content": user_msg})

    # --- COMPRESSION LOGIC ---
    # Keep System Prompt [0] + Last 6 messages. 
    # Prevents token overflow and keeps context relevant.
    if len(history) > 7:
        history = [history[0]] + history[-6:]
        logger.info(f"Session {sid[:8]} history compressed.")

    def generate():
        yield f"data: {json.dumps({'type': 'ping'})}\n\n"
        
        full_text_accumulator = ""
        
        for event in call_inference_stream(history):
            if event.startswith("data: "):
                try:
                    d = json.loads(event[6:])
                    if d['type'] == 'token':
                        full_text_accumulator += d['content']
                except: pass
            yield event
        
        # Save final response to history (if it wasn't a hidden tool call)
        if full_text_accumulator and not full_text_accumulator.strip().startswith("{"):
            history.append({"role": "assistant", "content": full_text_accumulator})
            
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return Response(
        stream_with_context(generate()), 
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no', # Critical for Nginx/Heroku
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
    <title>KUSTX | Support Terminal</title>
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
            display: flex; /* Flex on desktop */
            flex-direction: column;
            gap: 20px;
        }
        @media(max-width: 768px) { .sidebar { display: none; } }

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
            <span>//</span> KUSTX
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
                    <p><strong>KustX Online.</strong></p>
                    <p>I am KustX. How can I help you?</p>
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
                            // ignore partial json
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
