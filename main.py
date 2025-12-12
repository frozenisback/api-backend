# main.py
# -----------------------------------------------------------------------------
# KUST BOTS PROFESSIONAL SUPPORT SYSTEM (Production Ready - SSE Streaming + Auto-Summary)
# Single-file Flask application with a modern, high-contrast, animated UI.
#
# DEPLOYMENT:
#   - Requires: pip install flask requests gunicorn
#   - Env Vars: INFERENCE_URL, INFERENCE_KEY, INFERENCE_MODEL_ID
#   - Run: gunicorn main:app --timeout 120 --workers 2 --threads 4
# -----------------------------------------------------------------------------

import os
import re
import json
import uuid
import time
import logging
import requests
from flask import Flask, request, jsonify, render_template_string, stream_with_context, Response

# -----------------------------------------------------------------------------
# 1. CONFIGURATION & LOGGING
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [KUST-SUPPORT] %(message)s"
)
logger = logging.getLogger(__name__)

INFERENCE_KEY = os.getenv("INFERENCE_KEY", "")
INFERENCE_MODEL_ID = os.getenv("INFERENCE_MODEL_ID", "")
BASE_URL = os.getenv("INFERENCE_URL", "")

# Validation
if not (INFERENCE_KEY and INFERENCE_MODEL_ID and BASE_URL):
    logger.warning("CRITICAL: Missing Env Vars. Bot will fail to reply.")

API_URL = f"{BASE_URL.rstrip('/')}/v1/chat/completions"
HEADERS = {
    "Authorization": f"Bearer {INFERENCE_KEY}",
    "Content-Type": "application/json"
}

# -----------------------------------------------------------------------------
# 2. KNOWLEDGE BASE
# -----------------------------------------------------------------------------
KB = {
    "products": {
        "stake_chat_farmer": {
            "name": "Stake Chat Farmer",
            "bot_link": "@kustchatbot",
            "summary": "Autonomous chat generator. Simulates human patterns (mood, context) to farm XP/levels.",
            "pricing": "Free 3-hour trial.",
            "notes": "Not a spam bot; supports all country servers. Multi-account support."
        },
        "stake_code_claimer": {
            "name": "Stake Code Claimer",
            "summary": "Monitors channels and auto-claims codes instantly 24/7.",
            "features": ["Instant detection", "Multi-account redeem", "24/7 uptime"]
        },
        "frozen_music": {
            "name": "Frozen Music Bot",
            "summary": "High-performance distributed VC music bot.",
            "commands": {
                "/play": "Play audio",
                "/vplay": "Play video+audio",
                "/playlist": "Manage list",
                "/couple": "Daily match"
            },
            "plans": {
                "Tier 1": "$4/mo (5 VCs)",
                "Tier 2": "$8/mo (15 VCs)",
                "Tier 3": "$20/mo (50 VCs)"
            }
        },
        "kustify": {
            "name": "Kustify Hosting",
            "bot_link": "@kustifybot",
            "summary": "Bot hosting platform. Deploy via Telegram.",
            "plans": {
                "Ember": "$1.44/mo (0.25 CPU/512MB)",
                "Flare": "$2.16/mo (0.5 CPU/1GB)",
                "Inferno": "$3.60/mo (1 CPU/2GB)"
            }
        },
        "custom_bots": {
            "name": "Custom Development",
            "summary": "Bespoke bots. Commands start at $2-$5. White-label music bots available."
        }
    },
    "compliance": {
        "official": ["@kustbots", "@kustbotschat", "@KustDev"],
        "rules": [
            "NO gambling promos/bonuses.",
            "NO sales pushing.",
            "Verify official channels.",
            "Direct billing questions to Sparks/Payments."
        ]
    }
}

# -----------------------------------------------------------------------------
# 3. SYSTEM PROMPT
# -----------------------------------------------------------------------------
SYSTEM_PROMPT = """
You are Kust Assistant, the OFFICIAL support agent for Kust Bots.
Your style: Engineering-first, precise, professional, and helpful.

**CORE RULES:**
1. Official Only: @kustbots, @kustbotschat, @KustDev. Warn users about fakes.
2. No Gambling: Never discuss bonuses, drops, or gambling strategies.
3. No Sales: Explain pricing, but do not pressure.
4. Tools: You MUST use tools to get specific info.

**TOOL USAGE:**
To use a tool, output ONLY a JSON object:
{"tool": "get_kust_info", "query": "frozen music pricing"}
{"tool": "get_kust_info", "query": "stake farmer features"}

Do not write text before or after the JSON when calling a tool.
"""

# -----------------------------------------------------------------------------
# 4. FLASK APP & STATE
# -----------------------------------------------------------------------------
app = Flask(__name__)
CHAT_SESSIONS = {}

def get_history(user_id):
    if user_id not in CHAT_SESSIONS:
        CHAT_SESSIONS[user_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    return CHAT_SESSIONS[user_id]

def update_history(user_id, role, content):
    if not content: return
    CHAT_SESSIONS[user_id].append({"role": role, "content": str(content)})

# -----------------------------------------------------------------------------
# 5. MEMORY OPTIMIZATION (Fix for 400 Errors)
# -----------------------------------------------------------------------------
def summarize_history_if_needed(user_id):
    """
    Compresses chat history if it grows too long to prevent 400 Bad Request / Token Limits.
    """
    history = CHAT_SESSIONS.get(user_id, [])
    
    # If history > 12 messages, condense the middle
    if len(history) > 12:
        logger.info(f"Triggering auto-summarization for user {user_id}...")
        
        system_msg = history[0]
        recent_msgs = history[-3:]
        middle_chunk = history[1:-3]
        
        if not middle_chunk: return

        # Prepare text for summarization
        conversation_text = ""
        for msg in middle_chunk:
            conversation_text += f"{msg.get('role','unknown').upper()}: {msg.get('content','')}\n"
            
        summary_payload = {
            "model": INFERENCE_MODEL_ID,
            "messages": [
                {"role": "system", "content": "Compress this support chat into 2-3 sentences. Keep user details, errors reported, and products discussed."},
                {"role": "user", "content": conversation_text}
            ],
            "max_tokens": 200,
            "temperature": 0.3
        }
        
        try:
            r = requests.post(API_URL, json=summary_payload, headers=HEADERS, timeout=10)
            if r.status_code == 200:
                summary = r.json()["choices"][0]["message"]["content"]
                new_history = [system_msg]
                new_history.append({"role": "system", "content": f"[PREVIOUS CHAT SUMMARY]: {summary}"})
                new_history.extend(recent_msgs)
                CHAT_SESSIONS[user_id] = new_history
                logger.info("Chat compressed successfully.")
            else:
                CHAT_SESSIONS[user_id] = [system_msg] + recent_msgs
                logger.warning("Summarization failed. History truncated.")
        except Exception as e:
            logger.error(f"Summary Error: {e}")
            CHAT_SESSIONS[user_id] = [system_msg] + recent_msgs

# -----------------------------------------------------------------------------
# 6. TOOLS
# -----------------------------------------------------------------------------
def tool_get_kust_info(query):
    q = str(query).lower()
    p = KB["products"]
    
    if "farm" in q or "chat" in q: return json.dumps(p["stake_chat_farmer"])
    if "code" in q or "claim" in q: return json.dumps(p["stake_code_claimer"])
    if "music" in q or "play" in q or "frozen" in q: return json.dumps(p["frozen_music"])
    if "host" in q or "kustify" in q or "plan" in q: return json.dumps(p["kustify"])
    if "custom" in q: return json.dumps(p["custom_bots"])
    if "rule" in q or "fake" in q or "official" in q: return json.dumps(KB["compliance"])
    
    return json.dumps({"available": list(p.keys()), "note": "Please specify the product name."})

TOOLS = {"get_kust_info": tool_get_kust_info}

# -----------------------------------------------------------------------------
# 7. STREAMING LOGIC (The Core Engine)
# -----------------------------------------------------------------------------
def stream_inference(messages):
    """Yields chunks of text from the LLM. Handles 400 errors gracefully."""
    payload = {
        "model": INFERENCE_MODEL_ID,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 800,
        "stream": True
    }
    
    try:
        with requests.post(API_URL, json=payload, headers=HEADERS, stream=True, timeout=60) as r:
            if r.status_code == 400:
                logger.error(f"Inference 400 Error: {r.text}")
                yield "ERR_400"
                return

            r.raise_for_status()
            
            for line in r.iter_lines():
                if not line: continue
                line_text = line.decode('utf-8')
                if line_text.startswith("data: "):
                    data_str = line_text[6:]
                    if data_str == "[DONE]": break
                    try:
                        data_json = json.loads(data_str)
                        if "choices" in data_json and len(data_json["choices"]) > 0:
                            delta = data_json["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                    except:
                        pass
    except Exception as e:
        logger.error(f"Stream Error: {e}")
        yield f"[Error: {str(e)}]"

def process_chat_stream(user_id, user_message):
    """
    Orchestrates the conversation with auto-summary and retry logic.
    """
    history = get_history(user_id)
    update_history(user_id, "user", user_message)

    summarize_history_if_needed(user_id)
    history = get_history(user_id)

    for turn in range(3):
        buffer = ""
        is_tool_check = True
        tool_detected = False
        has_error = False
        
        stream_gen = stream_inference(history)
        
        for chunk in stream_gen:
            if chunk == "ERR_400":
                has_error = True
                break

            buffer += chunk
            
            if is_tool_check:
                stripped = buffer.lstrip()
                if not stripped: continue
                if stripped.startswith("{"):
                    continue
                else:
                    is_tool_check = False
                    yield f"data: {json.dumps({'type': 'token', 'content': buffer})}\n\n"
                    buffer = ""
            else:
                yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"

        if has_error:
            yield f"data: {json.dumps({'type': 'logic', 'content': 'Connection interrupted. Optimizing context...'})}\n\n"
            history = [history[0], history[-1]]
            CHAT_SESSIONS[user_id] = history
            stream_gen = stream_inference(history)
            for chunk in stream_gen:
                if chunk != "ERR_400":
                     yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"
            break

        if is_tool_check and buffer.strip().startswith("{"):
            try:
                clean_json = buffer.strip().strip("`").replace("json", "")
                tool_call = json.loads(clean_json)
                
                if "tool" in tool_call and tool_call["tool"] in TOOLS:
                    t_name = tool_call["tool"]
                    t_query = tool_call.get("query", "")
                    
                    yield f"data: {json.dumps({'type': 'logic', 'content': f'Fetching data from {t_name}...'})}\n\n"
                    
                    result = TOOLS[t_name](t_query)
                    
                    update_history(user_id, "assistant", buffer)
                    update_history(user_id, "system", f"[TOOL_OUTPUT]: {result}")
                    
                    tool_detected = True
                else:
                    yield f"data: {json.dumps({'type': 'token', 'content': buffer})}\n\n"
                    update_history(user_id, "assistant", buffer)
                    break 
            except:
                yield f"data: {json.dumps({'type': 'token', 'content': buffer})}\n\n"
                update_history(user_id, "assistant", buffer)
                break
        else:
            if buffer:
                yield f"data: {json.dumps({'type': 'token', 'content': buffer})}\n\n"
            break
        
        if not tool_detected:
            break

    yield f"data: {json.dumps({'type': 'done'})}\n\n"

# -----------------------------------------------------------------------------
# 8. ROUTES
# -----------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/api/chat_stream", methods=["POST"])
def chat_stream():
    data = request.json or {}
    user_id = data.get("user_id", "guest")
    message = data.get("message", "")
    
    if not message:
        return jsonify({"error": "empty message"}), 400

    return Response(
        stream_with_context(process_chat_stream(user_id, message)),
        mimetype='text/event-stream'
    )

@app.route("/api/reset", methods=["POST"])
def reset():
    data = request.json or {}
    uid = data.get("user_id")
    if uid in CHAT_SESSIONS:
        del CHAT_SESSIONS[uid]
    return jsonify({"status": "ok"})

# -----------------------------------------------------------------------------
# 9. PROFESSIONAL UI TEMPLATE
# -----------------------------------------------------------------------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kust Bots Support</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            /* Professional Dark Theme */
            --bg-body: #0f172a;
            --bg-sidebar: #1e293b;
            --bg-chat: #0f172a;
            --bg-message-bot: #1e293b;
            --bg-message-user: #3b82f6;
            --bg-logic: rgba(59, 130, 246, 0.1);
            
            --border-color: #334155;
            
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --text-accent: #60a5fa;
            
            --shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
            --shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1);
        }

        * { box-sizing: border-box; margin: 0; padding: 0; outline: none; }
        
        body {
            font-family: 'Inter', system-ui, -apple-system, sans-serif;
            background-color: var(--bg-body);
            color: var(--text-primary);
            height: 100vh;
            display: flex;
            overflow: hidden;
            font-size: 15px;
            line-height: 1.5;
        }

        /* --- SIDEBAR --- */
        .sidebar {
            width: 280px;
            background-color: var(--bg-sidebar);
            border-right: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
            padding: 24px;
            z-index: 10;
        }
        
        .brand {
            display: flex;
            align-items: center;
            gap: 12px;
            font-weight: 700;
            font-size: 18px;
            color: white;
            margin-bottom: 32px;
            letter-spacing: -0.025em;
        }
        
        .brand-icon {
            width: 32px; height: 32px;
            background: linear-gradient(135deg, #3b82f6, #2563eb);
            border-radius: 8px;
            display: flex; align-items: center; justify-content: center;
            font-size: 18px;
        }

        .nav-label {
            font-size: 12px;
            text-transform: uppercase;
            color: var(--text-secondary);
            font-weight: 600;
            margin-bottom: 12px;
            letter-spacing: 0.05em;
        }

        .nav-btn {
            background: transparent;
            border: 1px solid transparent;
            color: var(--text-primary);
            padding: 10px 12px;
            border-radius: 6px;
            text-align: left;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
            transition: all 0.2s ease;
            margin-bottom: 4px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .nav-btn:hover {
            background-color: rgba(255, 255, 255, 0.05);
            border-color: var(--border-color);
        }
        
        .nav-btn span { opacity: 0.7; }

        /* --- MAIN CHAT AREA --- */
        .main {
            flex: 1;
            display: flex;
            flex-direction: column;
            position: relative;
            background-color: var(--bg-chat);
        }

        .chat-container {
            flex: 1;
            overflow-y: auto;
            padding: 40px;
            display: flex;
            flex-direction: column;
            gap: 24px;
            scroll-behavior: smooth;
            max-width: 900px;
            margin: 0 auto;
            width: 100%;
        }
        
        .chat-container::-webkit-scrollbar { width: 6px; }
        .chat-container::-webkit-scrollbar-thumb { background: var(--border-color); border-radius: 3px; }
        .chat-container::-webkit-scrollbar-track { background: transparent; }

        /* --- MESSAGES --- */
        .msg-row {
            display: flex;
            width: 100%;
            animation: fadeIn 0.4s cubic-bezier(0.16, 1, 0.3, 1);
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .msg-row.user { justify-content: flex-end; }
        .msg-row.bot { justify-content: flex-start; }
        
        .avatar {
            width: 36px; height: 36px;
            border-radius: 50%;
            display: flex; align-items: center; justify-content: center;
            font-size: 18px;
            margin-right: 16px;
            flex-shrink: 0;
            background: var(--bg-message-bot);
            border: 1px solid var(--border-color);
            color: var(--text-secondary);
        }
        
        .msg-bubble {
            max-width: 85%;
            padding: 16px 20px;
            border-radius: 12px;
            font-size: 15px;
            line-height: 1.6;
            position: relative;
            box-shadow: var(--shadow-sm);
        }

        .msg-row.user .msg-bubble {
            background-color: var(--bg-message-user);
            color: white;
            border-bottom-right-radius: 4px;
        }

        .msg-row.bot .msg-bubble {
            background-color: var(--bg-message-bot);
            color: var(--text-primary);
            border: 1px solid var(--border-color);
            border-bottom-left-radius: 4px;
        }

        /* --- TOOL / LOGIC STATUS --- */
        .logic-status {
            display: inline-flex;
            align-items: center;
            gap: 10px;
            padding: 8px 16px;
            background: var(--bg-logic);
            border: 1px solid rgba(59, 130, 246, 0.2);
            border-radius: 20px;
            font-size: 13px;
            color: var(--text-accent);
            font-family: 'Inter', sans-serif;
            margin: 0 auto;
            animation: fadeIn 0.3s ease;
        }
        
        .pulse {
            width: 8px; height: 8px;
            background-color: var(--text-accent);
            border-radius: 50%;
            animation: pulse 1.5s infinite;
        }
        
        @keyframes pulse {
            0% { box-shadow: 0 0 0 0 rgba(96, 165, 250, 0.4); }
            70% { box-shadow: 0 0 0 6px rgba(96, 165, 250, 0); }
            100% { box-shadow: 0 0 0 0 rgba(96, 165, 250, 0); }
        }

        /* --- INPUT AREA --- */
        .input-container {
            padding: 24px;
            background-color: var(--bg-body);
            border-top: 1px solid var(--border-color);
            display: flex;
            justify-content: center;
        }
        
        .input-wrapper {
            max-width: 900px;
            width: 100%;
            position: relative;
            display: flex;
            align-items: center;
            background: var(--bg-sidebar);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 6px;
            transition: border-color 0.2s;
            box-shadow: var(--shadow-md);
        }
        
        .input-wrapper:focus-within {
            border-color: var(--text-accent);
        }

        input {
            flex: 1;
            background: transparent;
            border: none;
            color: white;
            padding: 14px 16px;
            font-family: 'Inter', sans-serif;
            font-size: 15px;
        }
        
        button.send-btn {
            background: var(--bg-message-user);
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            transition: opacity 0.2s;
            font-size: 14px;
        }
        
        button.send-btn:disabled { opacity: 0.5; cursor: not-allowed; }
        button.send-btn:hover:not(:disabled) { opacity: 0.9; }

        /* --- UTILS --- */
        .msg-bubble strong { font-weight: 600; color: white; }
        .msg-bubble code { 
            font-family: 'JetBrains Mono', monospace; 
            background: rgba(0,0,0,0.3); 
            padding: 2px 6px; 
            border-radius: 4px; 
            font-size: 0.9em;
            color: #e2e8f0;
        }
        
        /* Cursor Animation */
        .cursor {
            display: inline-block;
            width: 2px;
            height: 1.2em;
            background-color: var(--text-accent);
            margin-left: 2px;
            vertical-align: text-bottom;
            animation: blink 1s step-end infinite;
        }
        @keyframes blink { 50% { opacity: 0; } }
        
        /* Mobile */
        @media (max-width: 768px) {
            .sidebar { display: none; }
            .chat-container { padding: 20px; }
            .msg-bubble { max-width: 90%; }
        }
    </style>
</head>
<body>

    <!-- SIDEBAR -->
    <div class="sidebar">
        <div class="brand">
            <div class="brand-icon">K</div>
            Kust Bots
        </div>
        
        <div class="nav-label">Quick Queries</div>
        <button class="nav-btn" onclick="quickAsk('What are the Kustify hosting plans?')">
            <span>Server Plans</span>
        </button>
        <button class="nav-btn" onclick="quickAsk('How do I use the music bot?')">
            <span>Music Bot Commands</span>
        </button>
        <button class="nav-btn" onclick="quickAsk('Tell me about Chat Farmer features')">
            <span>Chat Farmer Info</span>
        </button>
        <button class="nav-btn" onclick="quickAsk('I need a custom bot developed')">
            <span>Custom Development</span>
        </button>

        <div style="margin-top: auto; border-top: 1px solid var(--border-color); padding-top: 20px;">
            <div style="font-size: 13px; color: var(--text-secondary); margin-bottom: 8px;">
                Session: <span id="uid" style="font-family: 'JetBrains Mono'; font-size: 11px;">...</span>
            </div>
            <button class="nav-btn" style="color: #ef4444; padding-left: 0;" onclick="reset()">
                Reset Conversation
            </button>
        </div>
    </div>

    <!-- MAIN CHAT -->
    <div class="main">
        <div class="chat-container" id="chat">
            <!-- Initial Bot Welcome -->
            <div class="msg-row bot">
                <div class="avatar">🤖</div>
                <div class="msg-bubble">
                    <strong>Support Online.</strong><br>
                    Welcome to the official Kust Bots support channel. I can help with hosting, music bots, or troubleshooting.<br>
                    <br>How can I assist you today?
                </div>
            </div>
        </div>
        
        <div class="input-container">
            <div class="input-wrapper">
                <input type="text" id="prompt" placeholder="Ask a question..." autocomplete="off">
                <button class="send-btn" id="sendBtn">Send</button>
            </div>
        </div>
    </div>

    <script>
        const uid = 'usr_' + Math.random().toString(36).substr(2,6);
        document.getElementById('uid').innerText = uid;
        const chat = document.getElementById('chat');
        const inp = document.getElementById('prompt');
        const btn = document.getElementById('sendBtn');
        let currentBotMsgBubble = null;
        let isGenerating = false;

        function addMsg(role, html) {
            const row = document.createElement('div');
            row.className = `msg-row ${role}`;
            
            if (role === 'bot') {
                row.innerHTML = `<div class="avatar">🤖</div><div class="msg-bubble">${html}</div>`;
            } else if (role === 'user') {
                row.innerHTML = `<div class="msg-bubble">${html}</div>`;
            } else if (role === 'logic') {
                // Logic is a centered status pill, not a standard message row
                row.style.justifyContent = 'center';
                row.innerHTML = `<div class="logic-status">${html}</div>`;
            }

            chat.appendChild(row);
            chat.scrollTop = chat.scrollHeight;
            
            if (role === 'bot') {
                // Return the bubble element inside so we can stream text into it
                return row.querySelector('.msg-bubble');
            }
            return row;
        }

        async function streamChat(text) {
            if(isGenerating) return;
            isGenerating = true;
            btn.disabled = true;
            btn.innerText = '...';
            
            addMsg('user', text);
            inp.value = '';

            try {
                const response = await fetch('/api/chat_stream', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ user_id: uid, message: text })
                });

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                
                // Initialize Bot Message
                currentBotMsgBubble = addMsg('bot', '<span id="stream-content"></span><span class="cursor"></span>');
                let contentSpan = currentBotMsgBubble.querySelector('#stream-content');
                let fullText = "";

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    
                    const chunk = decoder.decode(value);
                    const lines = chunk.split('\\n\\n');
                    
                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            const jsonStr = line.slice(6);
                            if(jsonStr === '[DONE]') break;
                            
                            try {
                                const data = JSON.parse(jsonStr);
                                
                                if (data.type === 'token') {
                                    fullText += data.content;
                                    const formatted = fullText
                                        .replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>')
                                        .replace(/\\n/g, '<br>');
                                    contentSpan.innerHTML = formatted;
                                    chat.scrollTop = chat.scrollHeight;
                                } 
                                else if (data.type === 'logic') {
                                    // Remove cursor from previous message chunk
                                    const oldCursor = currentBotMsgBubble.querySelector('.cursor');
                                    if(oldCursor) oldCursor.remove();
                                    
                                    // Show logic pill
                                    addMsg('logic', `<div class="pulse"></div> ${data.content}`);
                                    
                                    // Start NEW bot message bubble for post-tool text
                                    currentBotMsgBubble = addMsg('bot', '<span id="stream-content"></span><span class="cursor"></span>');
                                    contentSpan = currentBotMsgBubble.querySelector('#stream-content');
                                    fullText = "";
                                }
                            } catch (e) { console.error('JSON Parse Error', e); }
                        }
                    }
                }
                
                // Cleanup final cursor
                const finalCursor = currentBotMsgBubble.querySelector('.cursor');
                if(finalCursor) finalCursor.remove();

            } catch (err) {
                addMsg('bot', '<span style="color:#ef4444">Connection Error. Please try again.</span>');
            }
            
            isGenerating = false;
            btn.disabled = false;
            btn.innerText = 'Send';
            inp.focus();
        }

        function quickAsk(txt) { streamChat(txt); }
        function reset() { 
            fetch('/api/reset', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({user_id:uid})});
            chat.innerHTML = '';
            addMsg('bot', '<strong>Conversation Reset.</strong><br>How can I help you?');
        }

        btn.onclick = () => { if(inp.value.trim()) streamChat(inp.value.trim()); };
        inp.onkeydown = (e) => { if(e.key === 'Enter' && inp.value.trim()) streamChat(inp.value.trim()); };
    </script>
</body>
</html>
"""

# -----------------------------------------------------------------------------
# 10. RUNNER
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"KUST OS ONLINE : PORT {port}")
    app.run(host="0.0.0.0", port=port, threaded=True)
