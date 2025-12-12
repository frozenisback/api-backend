# main.py
# KUST BOTS OFFICIAL SUPPORT SYSTEM (Production Release - V5 KustX)
# Single-File Flask Application with Server-Sent Events (SSE) Streaming
# Features: Deep Knowledge Retrieval, Cyberpunk UI, Robust Error Handling.

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

# Environment Variables (Preserved)
INFERENCE_KEY = os.getenv("INFERENCE_KEY", "")
INFERENCE_MODEL_ID = os.getenv("INFERENCE_MODEL_ID", "")
BASE_URL = os.getenv("INFERENCE_URL", "")

# Fallback for local testing (remove in production if strictness required)
if not (INFERENCE_KEY and INFERENCE_MODEL_ID and BASE_URL):
    logger.warning("⚠️ WARNING: Missing INFERENCE env vars. Ensure they are set in production.")

API_URL = f"{BASE_URL.rstrip('/')}/v1/chat/completions" if BASE_URL else ""
HEADERS = {
    "Authorization": f"Bearer {INFERENCE_KEY}",
    "Content-Type": "application/json"
}

# ----------------------------
# 2. Comprehensive Knowledge Base
# ----------------------------
# Integrated from your provided text file
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
      ]
    },
    "frozen_music_bot": {
      "display_name": "Frozen Music (VC Music Bot)",
      "description": "Main voice-chat (VC) music bot with multi-source streaming and a distributed playback backend.",
      "core_commands": {
        "music": [
          "/play <song name or URL> - plays song from YT/Spotify/Resso/Apple/SoundCloud",
          "/vplay <url | query> - plays video + audio",
          "/playlist - view/manage playlists",
          "/skip - skip current (admin only)",
          "/pause, /resume, /stop - playback controls"
        ],
        "admin": ["/mute @user", "/unmute @user", "/tmute @user <minutes>", "/kick @user", "/ban @user"],
        "utility": ["/ping - uptime", "/couple - daily cached random pair"]
      },
      "backend": "distributed nodes with metadata server, distribution server, playback nodes.",
      "support_tips": [
        "Ask for: bot username, chat id, exact command used, timestamp",
        "Common fixes: restart playback node, clear queue, re-cache thumbnail/metadata"
      ]
    },
    "kustify_hosting": {
      "display_name": "Kustify Hosting",
      "bot": "@kustifybot",
      "description": "Lightweight bot hosting with instant deployment.",
      "commands": ["/host", "/mybots", "/balance", "/logs", "/env", "/restart", "/stop", "/delete"],
      "pricing": {
        "ember": { "cpu": 0.25, "ram_mb": 512, "price_usd_per_month": 1.44 },
        "flare": { "cpu": 0.5, "ram_mb": 1024, "price_usd_per_month": 2.16 },
        "inferno": { "cpu": 1, "ram_mb": 2048, "price_usd_per_month": 3.60 },
        "standby_cost_sparks_per_day": 2
      },
      "support_tips": [
        "Ask for: instance id, last deploy log, requested plan",
        "Common fixes: check build log, increase RAM if OOM"
      ]
    },
    "paid_custom_bots": {
      "description": "Custom bot development service.",
      "pricing_guidelines": {
        "per_command": "2-5 USD depending on complexity",
        "music_bot_plans": [
          { "monthly": 4, "setup": 6, "vcs": "4-5" },
          { "monthly": 8, "setup": 10, "vcs": "approx 15" },
          { "monthly": 20, "setup": 25, "vcs": "approx 50" }
        ]
      }
    }
  },
  "support_rules": {
    "official_only": ["@kustbots", "@kustbotschat", "@KustDev"],
    "interaction": "Respond only to first two users if busy.",
    "prohibited": [
      "Never mention bonuses, drops, or gambling promotions",
      "Never initiate conversations with moderators",
      "Never promote off-platform financial transactions"
    ]
  },
  "templates": {
    "verify_official": "Please confirm you're on @kustbots or in @kustbotschat. All other channels are unofficial.",
    "request_logs": "Provide: bot username, chat id, exact command, timestamp (UTC), and a screenshot or raw logs.",
    "trial_unavailable": "Trial slots are full. Would you like to join the waitlist?",
    "payment": "We accept PayPal or manual Indian client processing."
  },
  "troubleshooting": {
    "music_playback": ["Verify CDN URL", "Restart playback node", "Check download server"],
    "hosting": ["Inspect build logs", "Increase RAM plan", "Redeploy with cleared cache"],
    "stake_tools": ["Rotate proxy/session", "Lower frequency", "Re-auth accounts"]
  }
}

SYSTEM_PROMPT = """
You are KustX, the official AI support for Kust Bots.

**IDENTITY:**
- Name: KustX
- Owner: @KustDev
- Official Channels: @kustbots, @kustbotschat

**PROTOCOL:**
1. **Professional & Hacker-Chic:** Speak concisely, professionally, but with a slight tech-savvy edge.
2. **Formatting:** Use Markdown. Use bullet points for lists. Code blocks for commands.
3. **Safety:** NEVER discuss gambling bonuses, drops, or predictions. If asked, say "I cannot discuss gambling specifics, only the automation tools."
4. **Tool Use:** You MUST use the `get_info` tool to fetch facts. 
   - Output ONLY strictly valid JSON for tools: `{"tool": "get_info", "query": "pricing"}`
   - Do NOT preface JSON with text.

**CONTEXT:**
- If the user greets you, introduce yourself briefly and ask how to help.
- If the user asks about "Stake Farmer", "Music Bot", or "Hosting", search for those terms.
"""

# ----------------------------
# 3. Flask App & Session Logic
# ----------------------------
app = Flask(__name__)
SESSIONS = {}

def get_session(sid):
    if sid not in SESSIONS:
        SESSIONS[sid] = [{"role": "system", "content": SYSTEM_PROMPT}]
    return SESSIONS[sid]

# ----------------------------
# 4. Logic & Tools
# ----------------------------
def search_kb(query):
    """
    Searches the nested KB dictionary for the query terms.
    Returns a stringified JSON of the relevant section or a summary.
    """
    query = query.lower()
    results = {}

    # Helper to recursively search dictionary
    def recursive_search(data, search_term, path=""):
        found = {}
        if isinstance(data, dict):
            for k, v in data.items():
                new_path = f"{path}.{k}" if path else k
                # Check key match
                if search_term in k.lower():
                    found[new_path] = v
                # Check value match (if string)
                elif isinstance(v, str) and search_term in v.lower():
                    found[new_path] = v
                # Recurse
                elif isinstance(v, (dict, list)):
                    sub_results = recursive_search(v, search_term, new_path)
                    if sub_results:
                        found.update(sub_results)
        elif isinstance(data, list):
            for i, item in enumerate(data):
                if isinstance(item, (str, dict, list)):
                     # robust check for string inside list
                    if isinstance(item, str) and search_term in item.lower():
                         found[f"{path}[{i}]"] = item
                    elif isinstance(item, (dict, list)):
                        sub_results = recursive_search(item, search_term, f"{path}[{i}]")
                        if sub_results:
                            found.update(sub_results)
        return found

    # 1. Direct High-Level Matching
    if "price" in query or "cost" in query:
        results['hosting_pricing'] = KB['products']['kustify_hosting'].get('pricing')
        results['custom_bot_pricing'] = KB['products']['paid_custom_bots'].get('pricing_guidelines')
        results['farmer_price'] = "Stake Farmer: Free 3-hour trial"
    elif "command" in query or "help" in query:
        results['music_commands'] = KB['products']['frozen_music_bot'].get('core_commands')
        results['hosting_commands'] = KB['products']['kustify_hosting'].get('commands')
    else:
        # 2. Broad Search
        hits = recursive_search(KB, query)
        # Limit hits to prevent token overflow
        count = 0
        for k, v in hits.items():
            if count > 5: break
            results[k] = v
            count += 1
    
    # If no specific hits, provide menu
    if not results:
        return json.dumps({
            "available_products": list(KB['products'].keys()),
            "tip": "Try asking about 'hosting', 'music bot', or 'stake farmer'."
        }, indent=2)

    return json.dumps(results, indent=2)

def call_inference_stream(messages):
    """
    Generator that streams response from AI, handles tool calls,
    and manages the conversation flow.
    """
    if not API_URL:
        yield f"data: {json.dumps({'type': 'error', 'content': 'API URL not configured.'})}\n\n"
        return

    payload = {
        "model": INFERENCE_MODEL_ID,
        "messages": messages,
        "stream": True,
        "temperature": 0.3 # Lower temp for more factual support responses
    }
    
    try:
        with requests.post(API_URL, json=payload, headers=HEADERS, stream=True, timeout=60) as r:
            if r.status_code != 200:
                err_msg = f"API Error: {r.status_code} - {r.text[:50]}"
                logger.error(err_msg)
                yield f"data: {json.dumps({'type': 'error', 'content': err_msg})}\n\n"
                return

            tool_buffer = ""
            is_collecting_tool = False
            
            # Simple buffer to detect if the VERY FIRST tokens are a JSON object (Tool Call)
            accumulated_start = ""
            checking_for_tool = True

            for line in r.iter_lines():
                if not line: continue
                line = line.decode('utf-8')
                
                if line.startswith('data:'):
                    data_str = line[5:].strip()
                    if data_str == '[DONE]': break
                    
                    try:
                        chunk_json = json.loads(data_str)
                        delta = chunk_json.get('choices', [{}])[0].get('delta', {}).get('content', '')
                        
                        if delta:
                            if checking_for_tool:
                                accumulated_start += delta
                                # If we have enough chars to guess if it's JSON
                                if len(accumulated_start.strip()) > 0:
                                    if accumulated_start.strip().startswith("{"):
                                        is_collecting_tool = True
                                        tool_buffer = accumulated_start
                                        checking_for_tool = False
                                    elif len(accumulated_start) > 5:
                                        # Clearly not JSON
                                        yield f"data: {json.dumps({'type': 'token', 'content': accumulated_start})}\n\n"
                                        accumulated_start = ""
                                        checking_for_tool = False
                            else:
                                if is_collecting_tool:
                                    tool_buffer += delta
                                else:
                                    yield f"data: {json.dumps({'type': 'token', 'content': delta})}\n\n"
                    except Exception:
                        pass

            # End of stream logic
            if is_collecting_tool:
                try:
                    # Attempt to parse the accumulated JSON tool call
                    tool_data = json.loads(tool_buffer)
                    tool_name = tool_data.get("tool")
                    query = tool_data.get("query")
                    
                    # 1. Notify Frontend: Tool Started
                    yield f"data: {json.dumps({'type': 'tool_start', 'tool': tool_name, 'input': query})}\n\n"
                    
                    # 2. Execute Logic
                    time.sleep(0.8) # Artificial delay for "Scanning" effect
                    if tool_name == "get_info":
                        tool_result = search_kb(query)
                    else:
                        tool_result = "Unknown tool."

                    # 3. Notify Frontend: Tool Ends
                    yield f"data: {json.dumps({'type': 'tool_end', 'result': 'Done'})}\n\n"

                    # 4. Feed result back to AI
                    new_messages = messages + [
                        {"role": "assistant", "content": tool_buffer},
                        {"role": "user", "content": f"SYSTEM: Database Search Results:\n{tool_result}\n\nUsing these results, answer the user."}
                    ]
                    # Recursively call stream with new context
                    yield from call_inference_stream(new_messages)
                    
                except json.JSONDecodeError:
                    # If it wasn't valid JSON, just flush it as text
                    yield f"data: {json.dumps({'type': 'token', 'content': tool_buffer})}\n\n"
            elif checking_for_tool and accumulated_start:
                # Flush any remaining start buffer
                yield f"data: {json.dumps({'type': 'token', 'content': accumulated_start})}\n\n"

    except Exception as e:
        logger.exception(f"Stream Exception: {e}")
        yield f"data: {json.dumps({'type': 'error', 'content': 'Connection lost. Please retry.'})}\n\n"

# ----------------------------
# 5. Routes
# ----------------------------
@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/chat/stream", methods=["POST"])
def chat_stream():
    data = request.json
    user_msg = data.get("message")
    sid = data.get("session_id", str(uuid.uuid4()))
    
    if not user_msg:
        return jsonify({"error": "No message"}), 400

    history = get_session(sid)
    history.append({"role": "user", "content": user_msg})

    # Rolling Window Context: System Prompt + Last 6 messages
    if len(history) > 7:
        history = [history[0]] + history[-6:]

    def generate():
        yield f"data: {json.dumps({'type': 'ping'})}\n\n"
        full_response = ""
        
        for event in call_inference_stream(history):
            if event.startswith("data: "):
                try:
                    d = json.loads(event[6:])
                    if d['type'] == 'token':
                        full_response += d['content']
                except: pass
            yield event
        
        # Only append to history if it was a valid text response (not just a tool call)
        if full_response and not full_response.strip().startswith("{"):
            history.append({"role": "assistant", "content": full_response})
        
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream', 
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

@app.route("/api/reset", methods=["POST"])
def reset():
    sid = request.json.get("session_id")
    if sid in SESSIONS:
        del SESSIONS[sid]
    return jsonify({"status": "cleared", "new_id": str(uuid.uuid4())})

# ----------------------------
# 6. High-Fidelity UI Template
# ----------------------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>KUSTX | COMMAND CENTER</title>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Inter:wght@300;400;600;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #030305;
            --sidebar: #09090b;
            --card: #121216;
            --border: #27272a;
            --primary: #6366f1; /* Indigo */
            --primary-glow: rgba(99, 102, 241, 0.4);
            --accent: #d946ef; /* Fuchsia */
            --text: #f4f4f5;
            --text-dim: #71717a;
            --success: #10b981;
            --font-ui: 'Inter', sans-serif;
            --font-mono: 'JetBrains Mono', monospace;
        }

        /* --- Base Reset & Layout --- */
        * { box-sizing: border-box; scrollbar-width: thin; scrollbar-color: var(--border) var(--bg); }
        body { margin: 0; background: var(--bg); color: var(--text); font-family: var(--font-ui); height: 100vh; display: flex; overflow: hidden; }
        
        /* --- Grid Background Effect --- */
        body::before {
            content: ""; position: absolute; top: 0; left: 0; right: 0; bottom: 0;
            background-image: linear-gradient(var(--border) 1px, transparent 1px), linear-gradient(90deg, var(--border) 1px, transparent 1px);
            background-size: 40px 40px; opacity: 0.05; z-index: -1; pointer-events: none;
        }

        /* --- Sidebar --- */
        .sidebar { width: 320px; background: var(--sidebar); border-right: 1px solid var(--border); padding: 24px; display: flex; flex-direction: column; gap: 24px; z-index: 10; transition: transform 0.3s ease; }
        .brand { font-family: var(--font-mono); font-weight: 800; font-size: 1.5rem; letter-spacing: -1px; display: flex; align-items: center; gap: 12px; color: #fff; text-shadow: 0 0 15px var(--primary-glow); }
        .brand span { color: var(--primary); }
        
        .status-panel { background: rgba(255,255,255,0.03); border: 1px solid var(--border); border-radius: 12px; padding: 16px; backdrop-filter: blur(5px); }
        .status-row { display: flex; align-items: center; justify-content: space-between; font-size: 0.85rem; margin-bottom: 8px; }
        .status-row:last-child { margin-bottom: 0; }
        .status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--text-dim); box-shadow: 0 0 0 0 rgba(255,255,255,0.1); }
        .status-dot.active { background: var(--success); box-shadow: 0 0 10px var(--success); animation: pulse-green 2s infinite; }
        .status-dot.busy { background: var(--accent); box-shadow: 0 0 10px var(--accent); animation: pulse-purple 1s infinite; }

        .shortcuts { display: flex; flex-direction: column; gap: 10px; }
        .shortcut-btn { 
            background: transparent; border: 1px solid var(--border); color: var(--text-dim); 
            padding: 12px 16px; border-radius: 8px; cursor: pointer; text-align: left; 
            font-family: var(--font-mono); font-size: 0.85rem; transition: all 0.2s; position: relative; overflow: hidden;
        }
        .shortcut-btn:hover { border-color: var(--primary); color: #fff; background: rgba(99, 102, 241, 0.05); transform: translateX(4px); }
        .shortcut-btn::before { content: ">"; margin-right: 8px; opacity: 0; transition: opacity 0.2s; color: var(--primary); }
        .shortcut-btn:hover::before { opacity: 1; }

        .footer { margin-top: auto; font-size: 0.75rem; color: var(--text-dim); border-top: 1px solid var(--border); padding-top: 16px; }

        /* --- Main Chat Area --- */
        .main { flex: 1; display: flex; flex-direction: column; position: relative; max-width: 100%; }
        .chat-view { flex: 1; overflow-y: auto; padding: 30px; display: flex; flex-direction: column; gap: 24px; scroll-behavior: smooth; }
        
        /* Messages */
        .msg { display: flex; gap: 16px; max-width: 800px; width: 100%; margin: 0 auto; opacity: 0; animation: fade-up 0.4s forwards; }
        .msg.user { flex-direction: row-reverse; }
        
        .avatar { 
            width: 40px; height: 40px; border-radius: 10px; flex-shrink: 0; 
            display: flex; align-items: center; justify-content: center; font-size: 1.2rem;
            background: var(--card); border: 1px solid var(--border);
        }
        .msg.bot .avatar { box-shadow: 0 0 15px rgba(99, 102, 241, 0.1); border-color: var(--primary); color: var(--primary); }
        .msg.user .avatar { border-color: var(--border); color: #fff; }

        .bubble { 
            background: var(--card); border: 1px solid var(--border); padding: 16px 20px; 
            border-radius: 12px; font-size: 0.95rem; line-height: 1.6; position: relative;
            box-shadow: 0 4px 20px rgba(0,0,0,0.2); max-width: 80%;
        }
        .msg.bot .bubble { border-top-left-radius: 2px; border-left: 2px solid var(--primary); }
        .msg.user .bubble { border-top-right-radius: 2px; background: #1e1e24; border-right: 2px solid var(--text-dim); text-align: right; }

        /* Markdown Styling */
        .bubble p { margin: 0 0 10px 0; } .bubble p:last-child { margin: 0; }
        .bubble code { background: rgba(0,0,0,0.3); padding: 2px 6px; border-radius: 4px; color: var(--accent); font-family: var(--font-mono); font-size: 0.9em; }
        .bubble pre { background: #000; padding: 12px; border-radius: 8px; overflow-x: auto; border: 1px solid var(--border); }
        .bubble ul { margin: 5px 0 5px 20px; padding: 0; }
        .bubble strong { color: #fff; font-weight: 600; }

        /* Tool Animation Card */
        .tool-indicator {
            max-width: 800px; margin: -10px auto 10px auto; padding: 0 0 0 60px;
            display: flex; align-items: center; gap: 10px;
            font-family: var(--font-mono); font-size: 0.8rem; color: var(--accent);
            opacity: 0; animation: fade-in 0.3s forwards;
        }
        .scan-line { height: 2px; flex: 1; background: linear-gradient(90deg, var(--accent), transparent); width: 50px; }
        
        /* Input Area */
        .input-region { 
            padding: 24px; background: rgba(3,3,5,0.8); backdrop-filter: blur(12px); 
            border-top: 1px solid var(--border); z-index: 20; 
        }
        .input-box { 
            max-width: 800px; margin: 0 auto; position: relative; background: var(--card); 
            border: 1px solid var(--border); border-radius: 12px; padding: 8px;
            display: flex; gap: 10px; transition: border-color 0.2s, box-shadow 0.2s;
        }
        .input-box:focus-within { border-color: var(--primary); box-shadow: 0 0 20px rgba(99, 102, 241, 0.15); }
        
        input { 
            flex: 1; background: transparent; border: none; padding: 12px 16px; color: #fff; 
            font-family: var(--font-ui); font-size: 1rem; outline: none; 
        }
        button.send-btn { 
            background: var(--primary); color: #fff; border: none; border-radius: 8px; 
            padding: 0 24px; font-weight: 600; cursor: pointer; transition: all 0.2s;
            text-transform: uppercase; letter-spacing: 1px; font-size: 0.8rem;
        }
        button.send-btn:hover { background: #4f46e5; box-shadow: 0 0 15px var(--primary-glow); }
        button.send-btn:disabled { background: var(--border); color: var(--text-dim); cursor: not-allowed; box-shadow: none; }

        /* Mobile Responsive */
        @media (max-width: 768px) {
            .sidebar { position: absolute; left: -100%; height: 100%; box-shadow: 10px 0 30px rgba(0,0,0,0.5); }
            .sidebar.open { left: 0; }
            .chat-view { padding: 16px; }
            .msg { gap: 10px; }
            .avatar { width: 32px; height: 32px; font-size: 1rem; }
            .mobile-header { display: flex; align-items: center; padding: 16px; border-bottom: 1px solid var(--border); justify-content: space-between; }
        }
        @media (min-width: 769px) { .mobile-header { display: none; } }

        /* Animations */
        @keyframes fade-up { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes fade-in { from { opacity: 0; } to { opacity: 1; } }
        @keyframes pulse-green { 0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.4); } 70% { box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); } 100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); } }
        @keyframes pulse-purple { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
        
        .thinking { display: flex; gap: 4px; align-items: center; height: 24px; }
        .dot { width: 4px; height: 4px; background: var(--text-dim); border-radius: 50%; animation: bounce 1.4s infinite ease-in-out both; }
        .dot:nth-child(1) { animation-delay: -0.32s; } .dot:nth-child(2) { animation-delay: -0.16s; }
        @keyframes bounce { 0%, 80%, 100% { transform: scale(0); } 40% { transform: scale(1); background: var(--primary); } }
    </style>
</head>
<body>
    <!-- Mobile Header -->
    <div class="mobile-header">
        <div class="brand"><span>//</span> KUSTX</div>
        <button onclick="toggleSidebar()" style="background:none; border:none; color:#fff; font-size:1.5rem;">☰</button>
    </div>

    <!-- Sidebar -->
    <div class="sidebar" id="sidebar">
        <div class="brand"><span>//</span> KUSTX <small style="font-size:0.5em; opacity:0.5; margin-top:5px;">v5.0</small></div>
        
        <div class="status-panel">
            <div class="status-row"><span>SYSTEM STATUS</span><div id="status-dot" class="status-dot active"></div></div>
            <div class="status-row"><span style="color:var(--text-dim)">Knowledge Base</span><span style="color:var(--success)">SYNCED</span></div>
            <div class="status-row"><span style="color:var(--text-dim)">Inference</span><span style="color:var(--success)">ONLINE</span></div>
        </div>

        <div class="shortcuts">
            <div style="font-size:0.75rem; color:var(--text-dim); text-transform:uppercase; letter-spacing:1px; margin-bottom:4px;">Quick Execute</div>
            <button class="shortcut-btn" onclick="ask('What are the hosting plans?')">Pricing Protocols</button>
            <button class="shortcut-btn" onclick="ask('How do I setup Stake Chat Farmer?')">Init Stake Farmer</button>
            <button class="shortcut-btn" onclick="ask('List commands for Frozen Music Bot')">Music Bot Cmds</button>
            <button class="shortcut-btn" onclick="ask('I have a playback issue with music bot')">Debug Playback</button>
        </div>

        <div class="footer">
            SESSION: <span id="sess-id" style="font-family:var(--font-mono); color:var(--primary)">INITIALIZING...</span><br>
            <a href="#" onclick="resetSession()" style="color:var(--text-dim); text-decoration:none; margin-top:8px; display:inline-block; border-bottom:1px dotted var(--text-dim);">[ TERMINATE SESSION ]</a>
        </div>
    </div>

    <!-- Main Interface -->
    <div class="main">
        <div class="chat-view" id="chat">
            <div class="msg bot">
                <div class="avatar">🤖</div>
                <div class="bubble">
                    <p><strong>System Initialized.</strong></p>
                    <p>I am KustX, the autonomous support interface for Kust Bots. Accessing secure knowledge base...</p>
                </div>
            </div>
        </div>
        
        <div class="input-region">
            <div class="input-box">
                <input type="text" id="userInput" placeholder="Enter command or query..." autocomplete="off">
                <button class="send-btn" id="sendBtn" onclick="sendMessage()">EXECUTE</button>
            </div>
        </div>
    </div>

<script>
    // --- Logic & State ---
    const uuid = () => Math.random().toString(36).substring(2) + Date.now().toString(36);
    let session_id = localStorage.getItem('kust_sid_v5') || uuid();
    localStorage.setItem('kust_sid_v5', session_id);
    document.getElementById('sess-id').innerText = session_id.substring(0,8).toUpperCase();

    const chatEl = document.getElementById('chat');
    const inputEl = document.getElementById('userInput');
    const sendBtn = document.getElementById('sendBtn');
    const statusDot = document.getElementById('status-dot');

    function toggleSidebar() { document.getElementById('sidebar').classList.toggle('open'); }
    function scrollToBottom() { chatEl.scrollTop = chatEl.scrollHeight; }

    function setBusy(busy) {
        if(busy) {
            statusDot.className = 'status-dot busy';
            sendBtn.disabled = true;
            inputEl.disabled = true;
            inputEl.style.opacity = '0.5';
        } else {
            statusDot.className = 'status-dot active';
            sendBtn.disabled = false;
            inputEl.disabled = false;
            inputEl.style.opacity = '1';
            inputEl.focus();
        }
    }

    // --- UI Builders ---
    function appendUserMsg(text) {
        const div = document.createElement('div');
        div.className = 'msg user';
        div.innerHTML = `<div class="avatar">👤</div><div class="bubble">${text.replace(/</g, "&lt;")}</div>`;
        chatEl.appendChild(div);
        scrollToBottom();
    }

    function createBotMsg() {
        const div = document.createElement('div');
        div.className = 'msg bot';
        div.innerHTML = `<div class="avatar">🤖</div><div class="bubble"><div class="thinking"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div></div>`;
        chatEl.appendChild(div);
        scrollToBottom();
        return div.querySelector('.bubble');
    }

    let activeToolEl = null;
    function showToolActivity(toolName, query) {
        if(activeToolEl) activeToolEl.remove();
        const div = document.createElement('div');
        div.className = 'tool-indicator';
        div.innerHTML = `<span>> ACCESSING DB: "${query}"</span><div class="scan-line"></div>`;
        chatEl.appendChild(div);
        activeToolEl = div;
        scrollToBottom();
    }

    // --- Core Interaction ---
    async function sendMessage() {
        const text = inputEl.value.trim();
        if(!text) return;
        
        inputEl.value = '';
        appendUserMsg(text);
        setBusy(true);

        const botBubble = createBotMsg();
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
            let buffer = "";

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n\n');
                buffer = lines.pop(); // Keep incomplete line

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.substring(6));
                            
                            if (data.type === 'tool_start') {
                                showToolActivity(data.tool, data.input);
                            }
                            else if (data.type === 'tool_end') {
                                if(activeToolEl) {
                                    activeToolEl.innerHTML = `<span>> DATA RETRIEVED</span> <span style="color:var(--success)">✓</span>`;
                                    setTimeout(() => { if(activeToolEl) activeToolEl.remove(); activeToolEl=null; }, 1500);
                                }
                            }
                            else if (data.type === 'token') {
                                if (isFirstToken) { 
                                    botBubble.innerHTML = ''; 
                                    isFirstToken = false; 
                                }
                                currentText += data.content;
                                botBubble.innerHTML = marked.parse(currentText);
                                scrollToBottom();
                            }
                            else if (data.type === 'error') {
                                botBubble.innerHTML = `<span style="color:#ef4444; font-family:var(--font-mono)">[SYSTEM ERROR]: ${data.content}</span>`;
                            }
                        } catch (e) { console.error(e); }
                    }
                }
            }
        } catch (err) {
            botBubble.innerHTML = `<span style="color:#ef4444">[NETWORK FAILURE]</span>`;
        } finally {
            setBusy(false);
        }
    }

    function ask(q) { inputEl.value = q; sendMessage(); }
    
    async function resetSession() {
        if(confirm("Confirm purge of session logs?")) {
            await fetch('/api/reset', {
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body: JSON.stringify({session_id})
            });
            location.reload();
        }
    }

    inputEl.addEventListener('keypress', (e) => { if (e.key === 'Enter') sendMessage(); });
</script>
</body>
</html>
"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🚀 KUST BOTS System v5.0 Starting on Port {port}")
    app.run(host="0.0.0.0", port=port, threaded=True)
