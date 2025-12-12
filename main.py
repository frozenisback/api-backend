# main.py
# -----------------------------------------------------------------------------
# KUST BOTS PREMIUM SUPPORT SYSTEM (Production Ready)
# Single-file Flask application with embedded "Cyber-SaaS" UI.
#
# DEPLOYMENT:
#   - Requires: pip install flask requests gunicorn
#   - Env Vars: INFERENCE_URL, INFERENCE_KEY, INFERENCE_MODEL_ID
#   - Run: gunicorn main:app --timeout 120 --workers 2 --threads 4
# -----------------------------------------------------------------------------

import os
import re
import time
import json
import uuid
import logging
import requests
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string, session

# -----------------------------------------------------------------------------
# 1. CONFIGURATION & LOGGING
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [KUST-SUPPORT] %(message)s"
)
logger = logging.getLogger(__name__)

# Load Environment Variables
INFERENCE_KEY = os.getenv("INFERENCE_KEY", "")
INFERENCE_MODEL_ID = os.getenv("INFERENCE_MODEL_ID", "")
BASE_URL = os.getenv("INFERENCE_URL", "")

# Validate Critical Config
if not (INFERENCE_KEY and INFERENCE_MODEL_ID and BASE_URL):
    logger.warning("CRITICAL: Missing Inference Env Vars (INFERENCE_KEY/URL/MODEL_ID). Bot will fail to reply.")

API_URL = f"{BASE_URL.rstrip('/')}/v1/chat/completions"
HEADERS = {
    "Authorization": f"Bearer {INFERENCE_KEY}",
    "Content-Type": "application/json"
}

# -----------------------------------------------------------------------------
# 2. KNOWLEDGE BASE (Product Data)
# -----------------------------------------------------------------------------
KB = {
    "products": {
        "stake_chat_farmer": {
            "name": "Stake Chat Farmer",
            "bot_link": "@kustchatbot",
            "summary": "Fully autonomous human-like chat generator. Simulates real human patterns (mood, context, anti-spam).",
            "features": [
                "Per-user memory & mood adaptation",
                "Context recognition",
                "Works on all Stake country servers",
                "Multi-account support",
                "24/7 autonomous operation"
            ],
            "pricing": "Free 3-hour trial available.",
            "notes": "Not a spam bot; designed for farming chat levels/XP legitimately."
        },
        "stake_code_claimer": {
            "name": "Stake Code Claimer",
            "summary": "Automated system to monitor channels and claim codes instantly.",
            "features": [
                "Monitors Stake Telegram channels",
                "Detects new codes instantly",
                "Auto-redeems across accounts",
                "Runs 24/7 without user input"
            ]
        },
        "frozen_music": {
            "name": "Frozen Music Bot",
            "summary": "High-performance VC music bot with distributed backend.",
            "commands": {
                "/play": "Play audio (YT/Spotify/Resso/Apple/SC)",
                "/vplay": "Play video + audio",
                "/playlist": "Manage playlist",
                "/skip": "Skip track",
                "/couple": "Pick random pair daily"
            },
            "admin_commands": ["/mute", "/unmute", "/kick", "/ban"],
            "tech": "Distributed backend, caching, multi-node infrastructure."
        },
        "kustify": {
            "name": "Kustify Hosting",
            "bot_link": "@kustifybot",
            "summary": "Premium bot hosting platform. Deploy via Telegram.",
            "plans": {
                "Ember": "0.25 CPU / 512MB RAM — $1.44/month",
                "Flare": "0.5 CPU / 1GB RAM — $2.16/month",
                "Inferno": "1 CPU / 2GB RAM — $3.60/month"
            },
            "billing": "Stops bots cost 2 sparks/day for standby.",
            "commands": ["/host", "/mybots", "/logs", "/env", "/balance", "/buysparks"]
        },
        "custom_bots": {
            "name": "Paid Custom Bots",
            "summary": "Bespoke development services.",
            "offerings": [
                "Custom Telegram bots",
                "Custom commands ($2-$5 depending on complexity)",
                "White-label music bots"
            ],
            "music_bot_pricing": {
                "Tier 1": "$4/mo + $6 setup (4-5 VCs)",
                "Tier 2": "$8/mo + $10 setup (~15 VCs)",
                "Tier 3": "$20/mo + $25 setup (~50 VCs)"
            }
        }
    },
    "compliance": {
        "official_channel": "@kustbots",
        "official_support": "@kustbotschat",
        "owner": "@KustDev",
        "rules": [
            "Never mention bonuses, drops, or gambling promos.",
            "Never start convo with moderator.",
            "Never push sales; only explain pricing.",
            "Warn users about fake accounts."
        ]
    }
}

# -----------------------------------------------------------------------------
# 3. SYSTEM PROMPT
# -----------------------------------------------------------------------------
SYSTEM_PROMPT = f"""
You are the OFFICIAL SUPPORT AGENT for Kust Bots.
Your name is Kust Assistant. You are engineering-first, professional, and precise.

**CORE IDENTITY:**
- Official Channel: @kustbots
- Official Support Group: @kustbotschat
- Owner: @KustDev
- ANY other channel/account is FAKE. Warn users immediately if they mention others.

**YOUR KNOWLEDGE BASE (Use Tools to access details):**
- Products: Stake Chat Farmer, Stake Code Claimer, Frozen Music Bot, Kustify Hosting, Custom Bots.
- Data Source: You have access to a tool `get_kust_info` to get specs/pricing.

**COMPLIANCE & BEHAVIOR (CRITICAL):**
1. **never mention any other brand else kustbots** 
2. **NO SALES PUSH:** Explain pricing clearly when asked, but do not "sell" or pressure.
3. **BRIEF & DIRECT:** Answers should be short (1-4 sentences). Use bullet points for lists.
4. **TECH FIRST:** If a user reports a bug, ask for: Bot Username, Error Log/Message, Screenshot.
5. **ESCALATION:** If you cannot help, tell them to contact @Kustdev or join @kustbotschat.

**TOOL USAGE:**
To get details, output a SINGLE JSON object:
{{"tool": "get_kust_info", "query": "kustify plans"}}
{{"tool": "get_kust_info", "query": "frozen music commands"}}

Wait for the [TOOL_OUTPUT] system message before replying to the user.
"""

# -----------------------------------------------------------------------------
# 4. FLASK APP & SESSION MANAGEMENT
# -----------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", str(uuid.uuid4()))
CHAT_SESSIONS = {}  # In-memory session store (user_id -> history list)

def get_session_history(user_id):
    if user_id not in CHAT_SESSIONS:
        CHAT_SESSIONS[user_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    # Safety: trim history if too long to prevent context overflow
    if len(CHAT_SESSIONS[user_id]) > 20:
        # Keep system prompt + last 10 messages
        CHAT_SESSIONS[user_id] = [CHAT_SESSIONS[user_id][0]] + CHAT_SESSIONS[user_id][-10:]
    return CHAT_SESSIONS[user_id]

# -----------------------------------------------------------------------------
# 5. TOOL FUNCTIONS
# -----------------------------------------------------------------------------
def tool_get_kust_info(query_str):
    """Smart search over the KB dictionary."""
    q = str(query_str).lower()
    
    # Direct mapping shortcuts
    if "farm" in q or "chat" in q: return json.dumps(KB["products"]["stake_chat_farmer"])
    if "code" in q or "claim" in q: return json.dumps(KB["products"]["stake_code_claimer"])
    if "music" in q or "play" in q or "frozen" in q: return json.dumps(KB["products"]["frozen_music"])
    if "host" in q or "kustify" in q or "plan" in q or "cost" in q: return json.dumps(KB["products"]["kustify"])
    if "custom" in q or "buy" in q: return json.dumps(KB["products"]["custom_bots"])
    if "rule" in q or "fake" in q or "official" in q: return json.dumps(KB["compliance"])
    
    # Fallback: Return list of products
    return json.dumps({
        "available_products": list(KB["products"].keys()),
        "official_channels": KB["compliance"]
    })

TOOLS = {
    "get_kust_info": tool_get_kust_info
}

# -----------------------------------------------------------------------------
# 6. INFERENCE ENGINE
# -----------------------------------------------------------------------------
def call_inference_engine(messages):
    """Handles the API call to the LLM."""
    payload = {
        "model": INFERENCE_MODEL_ID,
        "messages": messages,
        "temperature": 0.3, # Keep it precise
        "max_tokens": 512
    }
    
    try:
        r = requests.post(API_URL, json=payload, headers=HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()
        
        # Defensive parsing for various API formats
        if "choices" in data and len(data["choices"]) > 0:
            content = data["choices"][0].get("message", {}).get("content") or data["choices"][0].get("text")
            return True, content
        elif "output" in data:
            return True, data["output"]
            
        return False, "Empty response from model API."
        
    except Exception as e:
        logger.error(f"Inference Error: {e}")
        return False, str(e)

def parse_tool_call(text):
    """Extracts JSON tool calls from text."""
    try:
        # Look for { ... } structure
        match = re.search(r'(\{.*"tool".*\})', text, re.DOTALL)
        if match:
            clean_json = match.group(1).replace("'", '"') # Basic cleanup
            data = json.loads(clean_json)
            if "tool" in data:
                return data
    except:
        pass
    return None

# -----------------------------------------------------------------------------
# 7. ROUTES
# -----------------------------------------------------------------------------

@app.route("/", methods=["GET"])
def index():
    """Serves the Premium UI."""
    return render_template_string(HTML_TEMPLATE)

@app.route("/api/chat", methods=["POST"])
def chat_endpoint():
    data = request.json or {}
    user_msg = data.get("message")
    user_id = data.get("user_id", "guest")
    
    if not user_msg:
        return jsonify({"error": "No message provided"}), 400
        
    history = get_session_history(user_id)
    history.append({"role": "user", "content": user_msg})
    
    events = [] # Log events to send to UI
    
    # --- Tool Execution Loop ---
    MAX_TURNS = 3
    final_response = ""
    
    for _ in range(MAX_TURNS):
        success, response_text = call_inference_engine(history)
        
        if not success:
            return jsonify({"error": "AI Service unavailable", "details": response_text}), 503
            
        # Check for Tool Call
        tool_req = parse_tool_call(response_text)
        
        if tool_req:
            t_name = tool_req.get("tool")
            t_query = tool_req.get("query")
            
            # Log for UI
            events.append({"type": "tool_use", "name": t_name, "status": "executing"})
            
            # Execute
            if t_name in TOOLS:
                t_result = TOOLS[t_name](t_query)
            else:
                t_result = json.dumps({"error": "Tool not found"})
                
            # Feed back to history
            history.append({"role": "assistant", "content": response_text})
            history.append({"role": "system", "content": f"[TOOL_OUTPUT]: {t_result}"})
            
            # Continue loop to let AI generate final answer
            continue
            
        else:
            # Final Answer
            history.append({"role": "assistant", "content": response_text})
            final_response = response_text
            break
            
    return jsonify({
        "response": final_response,
        "events": events
    })

@app.route("/api/reset", methods=["POST"])
def reset_session():
    data = request.json or {}
    user_id = data.get("user_id", "guest")
    if user_id in CHAT_SESSIONS:
        del CHAT_SESSIONS[user_id]
    return jsonify({"status": "cleared"})

# -----------------------------------------------------------------------------
# 8. PREMIUM FRONTEND (Embedded)
# -----------------------------------------------------------------------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kust Bots | Support Portal</title>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Inter:wght@300;400;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #030712;
            --panel: #0f172a;
            --border: #1e293b;
            --accent: #3b82f6;
            --accent-glow: rgba(59, 130, 246, 0.2);
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --user-bubble: #1e293b;
            --bot-bubble: #1e3a8a;
            --success: #10b981;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; outline: none; }
        
        body {
            font-family: 'Inter', sans-serif;
            background-color: var(--bg);
            color: var(--text-main);
            height: 100vh;
            display: flex;
            overflow: hidden;
        }

        /* --- Sidebar --- */
        .sidebar {
            width: 320px;
            background: var(--panel);
            border-right: 1px solid var(--border);
            display: flex;
            flex-direction: column;
            padding: 1.5rem;
            z-index: 10;
        }
        
        .brand {
            font-family: 'JetBrains Mono', monospace;
            font-size: 1.25rem;
            font-weight: 700;
            color: var(--accent);
            letter-spacing: -0.5px;
            margin-bottom: 0.5rem;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .brand-dot { width: 10px; height: 10px; background: var(--success); border-radius: 50%; box-shadow: 0 0 10px var(--success); }

        .desc {
            font-size: 0.85rem;
            color: var(--text-muted);
            margin-bottom: 2rem;
            line-height: 1.5;
        }

        .quick-actions {
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
        }

        .action-btn {
            background: rgba(255,255,255,0.03);
            border: 1px solid var(--border);
            color: var(--text-muted);
            padding: 0.85rem;
            border-radius: 8px;
            text-align: left;
            cursor: pointer;
            transition: all 0.2s;
            font-size: 0.9rem;
            font-family: 'JetBrains Mono', monospace;
        }

        .action-btn:hover {
            background: rgba(255,255,255,0.08);
            color: var(--text-main);
            border-color: var(--accent);
        }

        /* --- Main Chat Area --- */
        .main {
            flex: 1;
            display: flex;
            flex-direction: column;
            background: radial-gradient(circle at top right, #172033 0%, var(--bg) 40%);
            position: relative;
        }

        .chat-container {
            flex: 1;
            overflow-y: auto;
            padding: 2rem;
            display: flex;
            flex-direction: column;
            gap: 1.5rem;
            scroll-behavior: smooth;
        }
        
        .chat-container::-webkit-scrollbar { width: 6px; }
        .chat-container::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

        .msg {
            max-width: 80%;
            padding: 1rem 1.25rem;
            border-radius: 12px;
            line-height: 1.6;
            font-size: 0.95rem;
            animation: fadeUp 0.3s ease;
        }

        .msg.user {
            align-self: flex-end;
            background: var(--user-bubble);
            border: 1px solid var(--border);
            border-bottom-right-radius: 2px;
        }

        .msg.bot {
            align-self: flex-start;
            background: rgba(15, 23, 42, 0.8);
            border: 1px solid var(--border);
            border-left: 2px solid var(--accent);
            border-bottom-left-radius: 2px;
        }

        .msg.tool {
            align-self: center;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.8rem;
            color: var(--text-muted);
            background: rgba(0,0,0,0.2);
            padding: 0.5rem 1rem;
            border-radius: 20px;
            border: 1px dashed var(--border);
            margin: 0.5rem 0;
        }

        /* --- Input Area --- */
        .input-area {
            padding: 1.5rem 2rem;
            background: var(--bg);
            border-top: 1px solid var(--border);
            display: flex;
            gap: 1rem;
        }

        .input-box {
            flex: 1;
            background: var(--panel);
            border: 1px solid var(--border);
            color: white;
            padding: 1rem;
            border-radius: 8px;
            font-family: inherit;
            font-size: 1rem;
            transition: 0.2s;
        }

        .input-box:focus {
            border-color: var(--accent);
            box-shadow: 0 0 0 3px var(--accent-glow);
        }

        .send-btn {
            background: var(--accent);
            color: white;
            border: none;
            padding: 0 1.5rem;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            transition: 0.2s;
        }

        .send-btn:hover { opacity: 0.9; transform: translateY(-1px); }
        .send-btn:disabled { background: var(--border); cursor: not-allowed; }

        @keyframes fadeUp {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        @media (max-width: 768px) {
            body { flex-direction: column; }
            .sidebar { width: 100%; height: auto; padding: 1rem; display: none; } /* Hidden on mobile by default for simplicity */
            .main { height: 100vh; }
            .input-area { padding: 1rem; }
            .msg { max-width: 90%; }
        }
        
        /* Markdown-like styling inside messages */
        .msg strong { color: #fff; font-weight: 700; }
        .msg code { background: #000; padding: 2px 4px; border-radius: 4px; font-family: 'JetBrains Mono'; font-size: 0.85em; }
    </style>
</head>
<body>

    <div class="sidebar">
        <div class="brand">
            <div class="brand-dot"></div>
            KUST BOTS
        </div>
        <div class="desc">
            Official engineering-grade support system.
        </div>
        
        <div class="desc" style="margin-bottom: 0.5rem; font-weight: 600; color: #fff;">QUICK ACTIONS</div>
        <div class="quick-actions">
            <button class="action-btn" onclick="ask('What are the plans for Kustify?')">Hosting Plans</button>
            <button class="action-btn" onclick="ask('How does Frozen Music Bot work?')">Music Bot Info</button>
            <button class="action-btn" onclick="ask('Tell me about Stake Chat Farmer.')">Chat Farmer</button>
            <button class="action-btn" onclick="ask('I need a custom bot.')">Custom Services</button>
        </div>

        <div style="margin-top: auto; font-size: 0.75rem; color: var(--text-muted);">
            <p>Session ID: <span id="session-id">...</span></p>
            <button onclick="resetSession()" style="background:none; border:none; color: #ef4444; cursor:pointer; margin-top:10px; font-size:0.75rem;">[ Reset Session ]</button>
        </div>
    </div>

    <div class="main">
        <div class="chat-container" id="chat">
            <div class="msg bot">
                <strong>System Online.</strong><br>
                Welcome to Kust Bots Official Support.<br>
                I can assist with Kustify, Music Bots, Stake Tools, and Billing. How can I help?
            </div>
        </div>
        
        <div class="input-area">
            <input type="text" id="input" class="input-box" placeholder="Type your question here..." autocomplete="off">
            <button id="send-btn" class="send-btn">SEND</button>
        </div>
    </div>

    <script>
        const userId = 'user_' + Math.random().toString(36).substr(2, 9);
        document.getElementById('session-id').innerText = userId;
        
        const chat = document.getElementById('chat');
        const input = document.getElementById('input');
        const btn = document.getElementById('send-btn');

        function scrollToBottom() {
            chat.scrollTop = chat.scrollHeight;
        }

        function appendMessage(text, type) {
            const div = document.createElement('div');
            div.className = `msg ${type}`;
            // Simple markdown-ish rendering
            let html = text.replace(/\\n/g, '<br>')
                           .replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>'); 
            div.innerHTML = html;
            chat.appendChild(div);
            scrollToBottom();
        }
        
        function appendTool(text) {
            const div = document.createElement('div');
            div.className = 'msg tool';
            div.innerHTML = `<span style="color:#10b981">⚡ SYSTEM:</span> ${text}`;
            chat.appendChild(div);
            scrollToBottom();
        }

        async function ask(question) {
            if(!question) return;
            
            appendMessage(question, 'user');
            input.value = '';
            input.disabled = true;
            btn.disabled = true;
            btn.innerText = '...';

            try {
                const res = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: question, user_id: userId })
                });
                
                const data = await res.json();
                
                if (data.events) {
                    data.events.forEach(e => {
                        if(e.type === 'tool_use') {
                            appendTool(`Accessing Data: ${e.name}...`);
                        }
                    });
                }
                
                if (data.error) {
                    appendMessage(`Error: ${data.details || data.error}`, 'bot');
                } else {
                    appendMessage(data.response, 'bot');
                }
                
            } catch (e) {
                appendMessage("Connection error. Please try again.", 'bot');
            }

            input.disabled = false;
            btn.disabled = false;
            btn.innerText = 'SEND';
            input.focus();
        }

        async function resetSession() {
            await fetch('/api/reset', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({user_id: userId})
            });
            chat.innerHTML = '<div class="msg bot">Session Reset. System Ready.</div>';
        }

        btn.addEventListener('click', () => ask(input.value));
        input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') ask(input.value);
        });
    </script>
</body>
</html>
"""

# -----------------------------------------------------------------------------
# 9. ENTRY POINT
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"System Online. Listening on port {port}")
    app.run(host="0.0.0.0", port=port)
