# main.py
# -----------------------------------------------------------------------------
# KUST BOTS PROFESSIONAL SUPPORT SYSTEM (Production Ready)
# Single-file Flask application with robust streaming and polished UI.
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
# 5. MEMORY OPTIMIZATION
# -----------------------------------------------------------------------------
def summarize_history_if_needed(user_id):
    history = CHAT_SESSIONS.get(user_id, [])
    if len(history) > 12:
        system_msg = history[0]
        recent_msgs = history[-3:]
        middle_chunk = history[1:-3]
        if not middle_chunk: return

        conversation_text = ""
        for msg in middle_chunk:
            conversation_text += f"{msg.get('role','unknown').upper()}: {msg.get('content','')}\n"
            
        summary_payload = {
            "model": INFERENCE_MODEL_ID,
            "messages": [
                {"role": "system", "content": "Compress this support chat into 2-3 sentences. Keep details."},
                {"role": "user", "content": conversation_text}
            ],
            "max_tokens": 200,
            "temperature": 0.3
        }
        try:
            r = requests.post(API_URL, json=summary_payload, headers=HEADERS, timeout=10)
            if r.status_code == 200:
                summary = r.json()["choices"][0]["message"]["content"]
                new_history = [system_msg, {"role": "system", "content": f"[SUMMARY]: {summary}"}] + recent_msgs
                CHAT_SESSIONS[user_id] = new_history
        except Exception:
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
# 7. STREAMING LOGIC
# -----------------------------------------------------------------------------
def stream_inference(messages):
    """
    Yields chunks of text from the LLM. 
    Includes fallback for blank responses and permissive parsing.
    """
    payload = {
        "model": INFERENCE_MODEL_ID,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 800,
        "stream": True
    }
    
    yielded_any = False
    
    try:
        with requests.post(API_URL, json=payload, headers=HEADERS, stream=True, timeout=60) as r:
            if r.status_code != 200:
                logger.error(f"API Error {r.status_code}: {r.text}")
                yield f"[API Error: {r.status_code}]"
                return

            for line in r.iter_lines():
                if not line: continue
                line_text = line.decode('utf-8').strip()
                
                # Permissive parsing: match 'data:' with or without space
                if line_text.startswith("data:"):
                    data_str = line_text[5:].strip()
                    if data_str == "[DONE]": break
                    
                    try:
                        data_json = json.loads(data_str)
                        # Handle various API response formats
                        if "choices" in data_json and len(data_json["choices"]) > 0:
                            choice = data_json["choices"][0]
                            delta = choice.get("delta", {})
                            content = delta.get("content", "")
                            
                            if content:
                                yielded_any = True
                                yield content
                    except json.JSONDecodeError:
                        continue
    except Exception as e:
        logger.error(f"Stream Exception: {e}")
        yield f"[Connection Error: {str(e)}]"
        return

    # Fallback if stream finished but nothing was yielded (empty response)
    if not yielded_any:
        yield "..." # Sends a visual spacer so it's not totally blank

def process_chat_stream(user_id, user_message):
    history = get_history(user_id)
    update_history(user_id, "user", user_message)
    summarize_history_if_needed(user_id)
    history = get_history(user_id)

    # Signal UI that we are working
    yield f"data: {json.dumps({'type': 'logic', 'content': 'Analyzing query...'})}\n\n"

    for turn in range(3):
        buffer = ""
        is_tool_check = True
        tool_detected = False
        
        stream_gen = stream_inference(history)
        
        for chunk in stream_gen:
            buffer += chunk
            
            # Check for tool JSON at start of message
            if is_tool_check:
                stripped = buffer.lstrip()
                # If we have < 5 chars, wait for more to decide if it's JSON
                if len(stripped) < 5: 
                    if stripped and not stripped.startswith("{"):
                         # Definitely not JSON
                         is_tool_check = False
                         yield f"data: {json.dumps({'type': 'token', 'content': buffer})}\n\n"
                         buffer = ""
                    continue
                
                if stripped.startswith("{"):
                    # Looks like tool, keep buffering, don't stream to user
                    continue
                else:
                    # Not tool, flush buffer and stream normally
                    is_tool_check = False
                    yield f"data: {json.dumps({'type': 'token', 'content': buffer})}\n\n"
                    buffer = ""
            else:
                yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"

        # End of stream chunk processing
        if is_tool_check and buffer.strip().startswith("{"):
            try:
                # Attempt to execute tool
                clean_json = buffer.strip().strip("`").replace("json", "")
                tool_call = json.loads(clean_json)
                
                if "tool" in tool_call and tool_call["tool"] in TOOLS:
                    t_name = tool_call["tool"]
                    t_query = tool_call.get("query", "")
                    
                    yield f"data: {json.dumps({'type': 'logic', 'content': f'Fetching {t_name}...'})}\n\n"
                    
                    result = TOOLS[t_name](t_query)
                    update_history(user_id, "assistant", buffer)
                    update_history(user_id, "system", f"[TOOL_OUTPUT]: {result}")
                    tool_detected = True
                else:
                    # JSON but not tool, print it
                    yield f"data: {json.dumps({'type': 'token', 'content': buffer})}\n\n"
            except:
                # Failed parse, print raw
                yield f"data: {json.dumps({'type': 'token', 'content': buffer})}\n\n"
        else:
            # Just normal text remaining in buffer
            if buffer:
                yield f"data: {json.dumps({'type': 'token', 'content': buffer})}\n\n"
            
            if not is_tool_check and buffer:
                update_history(user_id, "assistant", buffer)
        
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
    if not message: return jsonify({"error": "empty message"}), 400

    return Response(
        stream_with_context(process_chat_stream(user_id, message)),
        mimetype='text/event-stream'
    )

@app.route("/api/reset", methods=["POST"])
def reset():
    data = request.json or {}
    uid = data.get("user_id")
    if uid in CHAT_SESSIONS: del CHAT_SESSIONS[uid]
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
            --bg-message-bot: #334155;
            --bg-message-user: #2563eb;
            --bg-logic: rgba(37, 99, 235, 0.15);
            
            --border-color: #334155;
            --text-primary: #f8fafc;
            --text-secondary: #cbd5e1;
            --text-accent: #60a5fa;
            
            --shadow-sm: 0 1px 3px 0 rgb(0 0 0 / 0.3);
        }

        * { box-sizing: border-box; margin: 0; padding: 0; outline: none; }
        
        body {
            font-family: 'Inter', sans-serif;
            background-color: var(--bg-body);
            color: var(--text-primary);
            height: 100vh;
            display: flex;
            overflow: hidden;
            font-size: 15px;
            line-height: 1.6;
        }

        /* SIDEBAR */
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

        .nav-btn {
            background: transparent;
            border: 1px solid transparent;
            color: var(--text-secondary);
            padding: 10px 12px;
            border-radius: 6px;
            text-align: left;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
            transition: all 0.2s;
            margin-bottom: 4px;
        }
        
        .nav-btn:hover {
            background-color: rgba(255, 255, 255, 0.05);
            color: white;
        }

        /* MAIN */
        .main {
            flex: 1;
            display: flex;
            flex-direction: column;
            background-color: var(--bg-chat);
        }

        .chat-container {
            flex: 1;
            overflow-y: auto;
            padding: 30px;
            display: flex;
            flex-direction: column;
            gap: 20px;
            scroll-behavior: smooth;
            max-width: 800px;
            margin: 0 auto;
            width: 100%;
        }
        
        .chat-container::-webkit-scrollbar { width: 6px; }
        .chat-container::-webkit-scrollbar-thumb { background: var(--border-color); border-radius: 3px; }

        /* MESSAGES */
        .msg-row {
            display: flex;
            width: 100%;
            animation: slideUp 0.3s cubic-bezier(0.2, 0.8, 0.2, 1);
        }
        
        @keyframes slideUp { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

        .msg-row.user { justify-content: flex-end; }
        .msg-row.bot { justify-content: flex-start; }
        
        .avatar {
            width: 32px; height: 32px;
            border-radius: 8px;
            display: flex; align-items: center; justify-content: center;
            font-size: 16px;
            margin-right: 12px;
            flex-shrink: 0;
            background: linear-gradient(135deg, #475569, #334155);
            color: white;
            box-shadow: var(--shadow-sm);
        }
        
        .msg-bubble {
            max-width: 85%;
            padding: 14px 18px;
            border-radius: 12px;
            font-size: 15px;
            position: relative;
            box-shadow: var(--shadow-sm);
            word-wrap: break-word;
        }

        .msg-row.user .msg-bubble {
            background-color: var(--bg-message-user);
            color: white;
            border-bottom-right-radius: 2px;
        }

        .msg-row.bot .msg-bubble {
            background-color: var(--bg-message-bot);
            color: var(--text-primary);
            border-bottom-left-radius: 2px;
        }

        .logic-pill {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 6px 14px;
            background: var(--bg-logic);
            border-radius: 20px;
            font-size: 12px;
            color: var(--text-accent);
            margin: 0 auto;
            animation: fadeIn 0.3s;
        }
        
        /* TYPING ANIMATIONS */
        .typing-dots {
            display: inline-block;
        }
        .typing-dots span {
            display: inline-block;
            width: 5px; height: 5px;
            background-color: #94a3b8;
            border-radius: 50%;
            margin: 0 2px;
            animation: wave 1s infinite;
        }
        .typing-dots span:nth-child(2) { animation-delay: 0.1s; }
        .typing-dots span:nth-child(3) { animation-delay: 0.2s; }
        
        @keyframes wave {
            0%, 60%, 100% { transform: translateY(0); }
            30% { transform: translateY(-5px); }
        }
        
        @keyframes blink { 50% { opacity: 0; } }
        .cursor {
            display: inline-block;
            width: 2px; height: 1.2em;
            background-color: var(--text-accent);
            vertical-align: middle;
            margin-left: 2px;
            animation: blink 1s step-end infinite;
        }

        /* INPUT */
        .input-container {
            padding: 24px;
            border-top: 1px solid var(--border-color);
            background: var(--bg-body);
            display: flex;
            justify-content: center;
        }
        
        .input-wrapper {
            max-width: 800px;
            width: 100%;
            display: flex;
            background: var(--bg-sidebar);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 6px;
            transition: 0.2s;
        }
        
        .input-wrapper:focus-within { border-color: var(--text-accent); }

        input {
            flex: 1;
            background: transparent;
            border: none;
            color: white;
            padding: 12px 16px;
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
            transition: 0.2s;
        }
        button.send-btn:hover { opacity: 0.9; }
        button.send-btn:disabled { background: #475569; cursor: not-allowed; }

        .msg-bubble strong { color: white; font-weight: 600; }
        .msg-bubble code { background: rgba(0,0,0,0.3); padding: 2px 5px; border-radius: 4px; font-family: 'JetBrains Mono', monospace; font-size: 0.9em; }
        
        @media (max-width: 768px) {
            .sidebar { display: none; }
            .chat-container { padding: 15px; }
            .msg-bubble { max-width: 90%; }
        }
    </style>
</head>
<body>

    <div class="sidebar">
        <div class="brand">
            <div class="brand-icon">K</div>
            Kust Bots
        </div>
        <button class="nav-btn" onclick="quickAsk('What are the Kustify plans?')">Server Plans</button>
        <button class="nav-btn" onclick="quickAsk('Music bot commands?')">Music Commands</button>
        <button class="nav-btn" onclick="quickAsk('Chat Farmer info?')">Chat Farmer</button>
        <div style="margin-top:auto">
            <button class="nav-btn" style="color:#ef4444" onclick="reset()">Reset Chat</button>
        </div>
    </div>

    <div class="main">
        <div class="chat-container" id="chat">
            <div class="msg-row bot">
                <div class="avatar">🤖</div>
                <div class="msg-bubble">
                    <strong>Support Online.</strong><br>
                    Welcome to Kust Bots. How can I help you today?
                </div>
            </div>
        </div>
        
        <div class="input-container">
            <div class="input-wrapper">
                <input type="text" id="prompt" placeholder="Type a message..." autocomplete="off">
                <button class="send-btn" id="sendBtn">Send</button>
            </div>
        </div>
    </div>

    <script>
        const uid = 'user_' + Math.random().toString(36).substr(2,6);
        const chat = document.getElementById('chat');
        const inp = document.getElementById('prompt');
        const btn = document.getElementById('sendBtn');
        let currentBotMsg = null;
        let isGenerating = false;

        function addMsg(role, content) {
            const row = document.createElement('div');
            if (role === 'logic') {
                row.style.textAlign = 'center';
                row.style.marginBottom = '10px';
                row.innerHTML = `<div class="logic-pill"><span>⚡</span> ${content}</div>`;
                chat.appendChild(row);
            } else {
                row.className = `msg-row ${role}`;
                const inner = role === 'bot' 
                    ? `<div class="avatar">🤖</div><div class="msg-bubble">${content}</div>`
                    : `<div class="msg-bubble">${content}</div>`;
                row.innerHTML = inner;
                chat.appendChild(row);
                if (role === 'bot') return row.querySelector('.msg-bubble');
            }
            chat.scrollTop = chat.scrollHeight;
        }

        async function streamChat(text) {
            if (isGenerating) return;
            isGenerating = true;
            btn.disabled = true;
            
            addMsg('user', text);
            inp.value = '';
            
            // Immediate feedback: "Thinking..." bubble
            currentBotMsg = addMsg('bot', '<div class="typing-dots"><span></span><span></span><span></span></div>');

            try {
                const res = await fetch('/api/chat_stream', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({user_id: uid, message: text})
                });

                const reader = res.body.getReader();
                const decoder = new TextDecoder();
                let fullText = "";
                let firstTokenReceived = false;

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    
                    const chunk = decoder.decode(value);
                    const lines = chunk.split('\\n\\n');
                    
                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            const jsonStr = line.slice(6);
                            if (jsonStr === '[DONE]') break;
                            
                            try {
                                const data = JSON.parse(jsonStr);
                                
                                if (data.type === 'token') {
                                    if (!firstTokenReceived) {
                                        // Clear "..." and start text
                                        currentBotMsg.innerHTML = '<span id="txt"></span><span class="cursor"></span>';
                                        firstTokenReceived = true;
                                    }
                                    fullText += data.content;
                                    const html = fullText
                                        .replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>')
                                        .replace(/\\n/g, '<br>');
                                    currentBotMsg.querySelector('#txt').innerHTML = html;
                                    chat.scrollTop = chat.scrollHeight;
                                } 
                                else if (data.type === 'logic') {
                                    // Remove old bubble if it was just typing dots
                                    if (!firstTokenReceived) currentBotMsg.parentNode.remove();
                                    
                                    addMsg('logic', data.content);
                                    
                                    // Start new bubble for response
                                    currentBotMsg = addMsg('bot', '<div class="typing-dots"><span></span><span></span><span></span></div>');
                                    firstTokenReceived = false;
                                    fullText = "";
                                }
                            } catch (e) {}
                        }
                    }
                }
                
                if (currentBotMsg && currentBotMsg.querySelector('.cursor')) {
                    currentBotMsg.querySelector('.cursor').remove();
                }

            } catch (e) {
                if (currentBotMsg) currentBotMsg.innerHTML = '<span style="color:#fca5a5">Connection Error. Please retry.</span>';
            }
            
            isGenerating = false;
            btn.disabled = false;
            inp.focus();
        }

        function quickAsk(t) { streamChat(t); }
        function reset() { 
            fetch('/api/reset', {method:'POST', body:JSON.stringify({user_id:uid}), headers:{'Content-Type':'application/json'}});
            chat.innerHTML = '';
            addMsg('bot', '<strong>Chat Reset.</strong><br>How can I help?');
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
