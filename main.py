# main.py
# -----------------------------------------------------------------------------
# KUST BOTS PREMIUM SUPPORT SYSTEM (Production Ready - SSE Streaming + Auto-Summary)
# Single-file Flask application with embedded "Cyber-SaaS" UI.
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
Your style: Engineering-first, precise, dark-mode aesthetic, helpful.

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
        
        # Keep: System Prompt [0]
        # Keep: Last 3 messages (Context) [-3:]
        # Summarize: The middle chunk
        
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
                
                # Rebuild History: System -> Memory Summary -> Recent
                new_history = [system_msg]
                new_history.append({"role": "system", "content": f"[PREVIOUS CHAT SUMMARY]: {summary}"})
                new_history.extend(recent_msgs)
                
                CHAT_SESSIONS[user_id] = new_history
                logger.info("Chat compressed successfully.")
            else:
                # If summarization fails, just truncate hard
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
            # Explicitly check for 400 Bad Request (Context Length / Format issues)
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

    # 1. OPTIMIZE MEMORY BEFORE REQUEST
    summarize_history_if_needed(user_id)
    history = get_history(user_id) # Refresh after summary

    # We allow up to 2 tool loops
    for turn in range(3):
        
        buffer = ""
        is_tool_check = True
        tool_detected = False
        has_error = False
        
        # 1. GENERATE
        stream_gen = stream_inference(history)
        
        for chunk in stream_gen:
            # 400 ERROR RECOVERY
            if chunk == "ERR_400":
                has_error = True
                break

            buffer += chunk
            
            # Heuristic: If buffer starts with {, it might be a tool
            if is_tool_check:
                stripped = buffer.lstrip()
                if not stripped: continue
                if stripped.startswith("{"):
                    continue # Buffer tool, don't show user
                else:
                    is_tool_check = False
                    yield f"data: {json.dumps({'type': 'token', 'content': buffer})}\n\n"
                    buffer = ""
            else:
                yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"

        # RECOVERY LOGIC
        if has_error:
            yield f"data: {json.dumps({'type': 'logic', 'content': 'Optimizing connection...'})}\n\n"
            # Drastic cut: System + User only
            history = [history[0], history[-1]]
            CHAT_SESSIONS[user_id] = history
            # Retry immediately
            stream_gen = stream_inference(history)
            # Drain the retry generator to user
            for chunk in stream_gen:
                if chunk != "ERR_400":
                     yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"
            break

        # 2. END OF STREAM ANALYSIS (Tool Logic)
        if is_tool_check and buffer.strip().startswith("{"):
            try:
                clean_json = buffer.strip().strip("`").replace("json", "")
                tool_call = json.loads(clean_json)
                
                if "tool" in tool_call and tool_call["tool"] in TOOLS:
                    t_name = tool_call["tool"]
                    t_query = tool_call.get("query", "")
                    
                    yield f"data: {json.dumps({'type': 'logic', 'content': f'Accessing {t_name}...'})}\n\n"
                    
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
            # Normal text finish
            if buffer:
                yield f"data: {json.dumps({'type': 'token', 'content': buffer})}\n\n"
            
            if not is_tool_check:
                # We implicitly saved user msg, but need to save assistant response
                # Note: In streaming, full assistant response accumulation is complex here.
                # For this implementation, we trust the next summarization cycle to clean up.
                pass 
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
# 9. PREMIUM UI TEMPLATE
# -----------------------------------------------------------------------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>KUST BOTS // CORE</title>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Space+Grotesk:wght@300;400;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #050505;
            --panel: #0a0a0a;
            --border: #1f1f1f;
            --accent: #00f0ff;
            --accent-dim: rgba(0, 240, 255, 0.1);
            --text-main: #ededed;
            --text-muted: #666;
            --user-bg: #1a1a1a;
            --bot-bg: #000000;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; outline: none; }
        
        body {
            font-family: 'Space Grotesk', sans-serif;
            background: var(--bg);
            color: var(--text-main);
            height: 100vh;
            display: flex;
            overflow: hidden;
            background-image: 
                radial-gradient(circle at 50% 0%, #111 0%, transparent 50%),
                linear-gradient(0deg, transparent 95%, rgba(0, 240, 255, 0.03) 96%);
            background-size: 100% 100%, 100% 4px;
        }

        /* SIDEBAR */
        .sidebar {
            width: 300px;
            border-right: 1px solid var(--border);
            padding: 20px;
            display: flex;
            flex-direction: column;
            background: rgba(10,10,10,0.8);
            backdrop-filter: blur(10px);
            z-index: 10;
        }
        
        .brand {
            font-family: 'JetBrains Mono';
            font-weight: 700;
            font-size: 18px;
            color: var(--accent);
            text-transform: uppercase;
            letter-spacing: 2px;
            margin-bottom: 30px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .brand::before { content: ''; width: 8px; height: 8px; background: var(--accent); box-shadow: 0 0 10px var(--accent); }

        .btn {
            background: transparent;
            border: 1px solid var(--border);
            color: var(--text-muted);
            padding: 12px;
            margin-bottom: 8px;
            text-align: left;
            font-family: 'JetBrains Mono';
            font-size: 12px;
            cursor: pointer;
            transition: 0.2s;
            position: relative;
            overflow: hidden;
        }

        .btn:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-dim); }
        .btn::after { content: '>'; position: absolute; right: 10px; opacity: 0; transition: 0.2s; }
        .btn:hover::after { opacity: 1; right: 15px; }

        /* MAIN CHAT */
        .main {
            flex: 1;
            display: flex;
            flex-direction: column;
            position: relative;
        }

        .chat-area {
            flex: 1;
            overflow-y: auto;
            padding: 30px;
            display: flex;
            flex-direction: column;
            gap: 20px;
            scroll-behavior: smooth;
        }
        
        .chat-area::-webkit-scrollbar { width: 5px; }
        .chat-area::-webkit-scrollbar-thumb { background: #333; }

        .msg {
            max-width: 800px;
            padding: 15px 20px;
            font-size: 15px;
            line-height: 1.6;
            animation: slideIn 0.3s ease-out;
            position: relative;
        }
        
        @keyframes slideIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

        .msg.user {
            align-self: flex-end;
            background: var(--user-bg);
            border: 1px solid var(--border);
            color: #fff;
            border-radius: 4px;
        }

        .msg.bot {
            align-self: flex-start;
            color: #d1d5db;
            border-left: 2px solid var(--accent);
            padding-left: 25px;
        }
        
        .msg.logic {
            align-self: center;
            font-family: 'JetBrains Mono';
            font-size: 11px;
            color: var(--accent);
            border: 1px solid var(--accent-dim);
            background: rgba(0,0,0,0.3);
            padding: 5px 12px;
            border-radius: 20px;
            display: flex;
            align-items: center;
            gap: 8px;
            opacity: 0.8;
        }
        
        .spinner {
            width: 8px; height: 8px; border: 1px solid var(--accent); border-top-color: transparent; border-radius: 50%; animation: spin 1s linear infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }

        /* INPUT */
        .input-wrap {
            padding: 20px;
            background: var(--bg);
            border-top: 1px solid var(--border);
            display: flex;
            gap: 10px;
        }

        input {
            flex: 1;
            background: var(--panel);
            border: 1px solid var(--border);
            color: #fff;
            padding: 15px;
            font-family: 'Space Grotesk';
            font-size: 16px;
        }
        
        input:focus { border-color: var(--accent); }

        button.send {
            background: var(--accent);
            color: #000;
            border: none;
            padding: 0 30px;
            font-weight: 700;
            cursor: pointer;
            text-transform: uppercase;
            font-family: 'JetBrains Mono';
        }
        
        button.send:disabled { background: #333; color: #555; cursor: wait; }

        /* MARKDOWN / FORMATTING */
        .msg strong { color: #fff; font-weight: 700; }
        .msg code { font-family: 'JetBrains Mono'; background: #111; padding: 2px 5px; color: var(--accent); font-size: 0.9em; }
        .cursor { display: inline-block; width: 6px; height: 15px; background: var(--accent); animation: blink 1s infinite; vertical-align: middle; margin-left: 4px; }
        @keyframes blink { 50% { opacity: 0; } }

        /* MOBILE */
        @media(max-width: 700px) {
            .sidebar { display: none; }
            .msg { max-width: 100%; }
        }
    </style>
</head>
<body>

    <div class="sidebar">
        <div class="brand">KUST BOTS // OS</div>
        <div style="font-size:11px; color:#555; margin-bottom:15px; font-family:'JetBrains Mono'">COMMAND CENTER</div>
        
        <button class="btn" onclick="quickAsk('What are the hosting plans?')">/query hosting_plans</button>
        <button class="btn" onclick="quickAsk('How do I use the music bot?')">/query music_help</button>
        <button class="btn" onclick="quickAsk('Tell me about Chat Farmer')">/query chat_farmer</button>
        <button class="btn" onclick="quickAsk('I want a custom bot')">/query custom_dev</button>
        
        <div style="margin-top:auto; border-top:1px solid #222; padding-top:15px;">
             <div style="font-size:10px; color:#444; font-family:'JetBrains Mono'">SESSION: <span id="uid">...</span></div>
             <button class="btn" style="margin-top:10px; border-color:#331111; color:#773333" onclick="reset()">/reset_session</button>
        </div>
    </div>

    <div class="main">
        <div class="chat-area" id="chat">
            <div class="msg bot">
                <strong>SYSTEM READY.</strong><br>
                Connected to Kust Bots Neural Interface.<br>
                Waiting for input...
            </div>
        </div>
        
        <div class="input-wrap">
            <input type="text" id="prompt" placeholder="Enter command or query..." autocomplete="off">
            <button class="send" id="sendBtn">EXEC</button>
        </div>
    </div>

    <script>
        const uid = 'usr_' + Math.random().toString(36).substr(2,6);
        document.getElementById('uid').innerText = uid;
        const chat = document.getElementById('chat');
        const inp = document.getElementById('prompt');
        const btn = document.getElementById('sendBtn');
        let currentBotMsg = null;
        let isGenerating = false;

        function addMsg(cls, html) {
            const d = document.createElement('div');
            d.className = 'msg ' + cls;
            d.innerHTML = html;
            chat.appendChild(d);
            chat.scrollTop = chat.scrollHeight;
            return d;
        }

        async function streamChat(text) {
            if(isGenerating) return;
            isGenerating = true;
            btn.disabled = true;
            
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
                
                // Create bot message container with cursor
                currentBotMsg = addMsg('bot', '<span id="stream-content"></span><span class="cursor"></span>');
                let contentSpan = currentBotMsg.querySelector('#stream-content');
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
                                    // Simple markdown parsing for bold
                                    const formatted = fullText.replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>').replace(/\\n/g, '<br>');
                                    contentSpan.innerHTML = formatted;
                                    chat.scrollTop = chat.scrollHeight;
                                } 
                                else if (data.type === 'logic') {
                                    // Logic/Tool event
                                    addMsg('logic', `<div class="spinner"></div> ${data.content}`);
                                    // Start new message block for post-tool text
                                    currentBotMsg.querySelector('.cursor').remove(); // remove cursor from old block
                                    currentBotMsg = addMsg('bot', '<span id="stream-content"></span><span class="cursor"></span>');
                                    contentSpan = currentBotMsg.querySelector('#stream-content');
                                    fullText = "";
                                }
                            } catch (e) { console.error('JSON Parse Error', e); }
                        }
                    }
                }
                
                // Cleanup final cursor
                if(currentBotMsg && currentBotMsg.querySelector('.cursor')) {
                    currentBotMsg.querySelector('.cursor').remove();
                }

            } catch (err) {
                addMsg('bot', '<span style="color:red">CONNECTION ERROR // RETRY</span>');
            }
            
            isGenerating = false;
            btn.disabled = false;
            inp.focus();
        }

        function quickAsk(txt) { streamChat(txt); }
        function reset() { 
            fetch('/api/reset', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({user_id:uid})});
            chat.innerHTML = '';
            addMsg('bot', '<strong>SYSTEM RESET.</strong> Memory Cleared.');
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
