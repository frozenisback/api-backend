# main.py
# Complete single-file Flask app — support assistant with tool-execution capability and improved UI.
# Deploy as-is. Requires env vars: INFERENCE_URL, INFERENCE_KEY, INFERENCE_MODEL_ID
# Use Procfile with gunicorn for production on Heroku:
# web: gunicorn main:app --timeout 300 --keep-alive 25 --workers 1 --threads 4

import os
import re
import time
import json
import logging
import requests
from flask import Flask, request, jsonify, render_template_string

# ----------------------------
# Logging
# ----------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("kust-support-tools")

# ----------------------------
# Env / Inference config
# ----------------------------
INFERENCE_KEY = os.getenv("INFERENCE_KEY")
INFERENCE_MODEL_ID = os.getenv("INFERENCE_MODEL_ID")
BASE_URL = os.getenv("INFERENCE_URL")

if not (INFERENCE_KEY and INFERENCE_MODEL_ID and BASE_URL):
    logger.warning("One or more inference env vars are missing (INFERENCE_KEY, INFERENCE_MODEL_ID, INFERENCE_URL).")

API_URL = f"{BASE_URL.rstrip('/')}/v1/chat/completions"
HEADERS = {"Authorization": f"Bearer {INFERENCE_KEY}", "Content-Type": "application/json"}

# ----------------------------
# Knowledge base (tools data)
# Keep this updated — the assistant can call tools to fetch these details.
# ----------------------------
KB = {
    "projects": {
        "frozen_music": {
            "name": "Frozen Music",
            "summary": "High-performance Telegram VC music bot (vcmusiclubot). Distributed playback system, caching, Cloudflare Workers routing, pre-cache when queueing for instant playback.",
            "commands": {
                "play": "Add a song to the queue. Usage: /play <title>",
                "stop": "Stop playback and clear the queue. Usage: /stop",
                "skip": "Skip current track. Usage: /skip",
                "queue": "Show current queue. Usage: /queue",
                "vol": "Set volume. Usage: /vol <0-100>"
            },
            "notes": "Supports distributed playback nodes with fallback servers and pre-caching. Deployed in 30 parts. Uses metadata server and download distribution fallback to yt-dlp."
        },
        "kustify": {
            "name": "Kustify Hosting",
            "summary": "Telegram bot hosting by Kust Bots. Dirt-cheap plans with instant deployment and auto-restore features.",
            "plans": {
                "ember": "0.25 CPU / 512MB RAM — $1.44/month",
                "flare": "0.5 CPU / 1GB RAM — $2.16/month",
                "inferno": "1 CPU / 2GB RAM — $3.60/month"
            },
            "notes": "99.9% uptime, global routing, auto-restores/crash-proof, deploy via @kustifybot."
        },
        "dash_game": {
            "name": "Dash — Geometry Dash style",
            "summary": "Custom HTML Canvas + JS geometry-dash style prototype. Physics, obstacles, powerups, dynamic music sync, difficulty scaling. No engines used.",
            "play_url": "https://dash.kustbotsweb.workers.dev/",
            "notes": "Prototype stage; upcoming features include pattern-based levels and beat-synced obstacles."
        },
        "downloader_api": {
            "name": "YouTube Downloader API",
            "summary": "Flask + yt-dlp based audio/video downloader, low-resource, supports search and Spotify->YouTube resolution.",
            "notes": "Designed to be lightweight and stream audio compatible with py-tgcalls."
        }
    },
    "global_notes": "Kust Bots is an engineering-first team: fast, stable, and focused on backend and Telegram infra. Support tone is direct and no-nonsense."
}

# ----------------------------
# Flask app + in-memory sessions
# ----------------------------
app = Flask(__name__)
CHAT_SESSIONS = {}  # user_id -> list of messages (OpenAI chat format)

# ----------------------------
# System prompt instructing agent how to call tools
# ----------------------------
SYSTEM_PROMPT = """
You are Kust Bots Support Assistant. You are engineering-first, direct, and concise.

**TOOL USAGE PROTOCOL (READ CAREFULLY)**
- If you need up-to-date factual info about Kust Bots projects, commands, or documentation, CALL the tool by returning a single JSON object (no extra text) in your assistant response exactly like:
{"tool":"<tool_name>","input":{"query":"...","project":"<project_key>"}}

- Supported tool names:
  - "list_projects" -> no input required. Returns project keys and short names.
  - "get_project_info" -> input: {"project":"frozen_music"} returns detailed project description and notes.
  - "list_commands" -> input: {"project":"frozen_music"} returns commands and short usage strings.
  - "search_kb" -> input: {"query":"how to play music bot"} returns matching KB excerpts.

- After the server runs the tool, it will append the tool output into the conversation and call you again. You MUST then produce a normal user-facing reply using that tool result. Do not call the tool again unless you need additional info.

- When producing the final answer to the user, do NOT include raw JSON tool calls; produce normal readable text.

**TONE & FORMAT**
- Be short: 1-5 short sentences by default.
- If giving steps, number them "1: ...", "2: ...".
- Use "Needed: <question>" for clarifying questions.
- If escalation is required, output exactly: "Escalate: Open support ticket" followed by the data needed to open a ticket (one-line summary, steps to reproduce, logs to collect).
- Follow safety rules: no gambling promos, no DM-sales, no abusive shortforms.

End of system instructions.
"""

# ----------------------------
# Helper functions
# ----------------------------
def ensure_session(user_id: str):
    if user_id not in CHAT_SESSIONS:
        CHAT_SESSIONS[user_id] = [{"role": "system", "content": SYSTEM_PROMPT}]

def call_inference(messages, timeout=60):
    """Call inference endpoint with defensive parsing."""
    payload = {"model": INFERENCE_MODEL_ID, "messages": messages}
    try:
        r = requests.post(API_URL, json=payload, headers=HEADERS, timeout=timeout)
    except Exception as e:
        logger.exception("Inference call error")
        return False, f"request error: {e}", None
    logger.info("Inference HTTP %s", r.status_code)
    text = r.text
    logger.debug("Inference response text: %s", text[:2000])
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}: {text}", None
    try:
        data = r.json()
    except Exception as e:
        return False, f"invalid json: {e}", r.text
    # Try to extract content conservatively:
    content = None
    try:
        content = data["choices"][0]["message"]["content"]
    except Exception:
        # fallback attempts
        if isinstance(data.get("output"), list) and data["output"]:
            content = data["output"][0].get("content")
        elif isinstance(data.get("choices"), list) and data["choices"]:
            content = data["choices"][0].get("text") or data["choices"][0].get("message", {}).get("content")
    if content is None:
        return False, "could not extract assistant content", data
    return True, content, data

# Tool implementations — the server executes these when model requests them
def tool_list_projects(_input):
    projects = KB["projects"]
    out = [{"key": k, "name": projects[k]["name"]} for k in projects]
    return json.dumps({"projects": out}, ensure_ascii=False)

def tool_get_project_info(_input):
    proj = _input.get("project")
    if not proj:
        return json.dumps({"error": "missing project key"})
    p = KB["projects"].get(proj)
    if not p:
        return json.dumps({"error": f"project '{proj}' not found"})
    return json.dumps({"project": proj, "name": p.get("name"), "summary": p.get("summary"), "notes": p.get("notes"), "extra": p.get("plans") or p.get("commands") or {}}, ensure_ascii=False)

def tool_list_commands(_input):
    proj = _input.get("project")
    if not proj:
        return json.dumps({"error": "missing project key"})
    p = KB["projects"].get(proj)
    if not p:
        return json.dumps({"error": f"project '{proj}' not found"})
    cmds = p.get("commands") or {}
    return json.dumps({"project": proj, "commands": cmds}, ensure_ascii=False)

def tool_search_kb(_input):
    q = (_input.get("query") or "").lower()
    results = []
    for k, v in KB["projects"].items():
        hay = " ".join([v.get("name",""), v.get("summary",""), v.get("notes","")]).lower()
        if q in hay:
            results.append({"project": k, "name": v.get("name"), "excerpt": v.get("summary")})
    # fallback: global notes
    if "kust" in q or "support" in q:
        results.append({"global": KB.get("global_notes")})
    return json.dumps({"query": q, "results": results}, ensure_ascii=False)

TOOLS = {
    "list_projects": tool_list_projects,
    "get_project_info": tool_get_project_info,
    "list_commands": tool_list_commands,
    "search_kb": tool_search_kb
}

# Parse assistant content to see if it requested a tool call (JSON object)
TOOL_JSON_RE = re.compile(r'^\s*({\s*"tool"\s*:\s*".+?"\s*,.*})\s*$', re.DOTALL)

def parse_tool_call(text: str):
    """
    If assistant returns a pure JSON object describing a tool call, return parsed dict.
    Example expected:
    {"tool":"get_project_info","input":{"project":"frozen_music"}}
    """
    # Try to locate a JSON object; prefer whole content JSON.
    text = text.strip()
    # Quick heuristic: if text starts with { and contains "tool"
    if text.startswith("{") and '"tool"' in text:
        try:
            obj = json.loads(text)
            if isinstance(obj, dict) and "tool" in obj:
                return obj
        except Exception:
            pass
    # fallback regex to extract a block that looks like a JSON with "tool"
    m = TOOL_JSON_RE.search(text)
    if m:
        try:
            obj = json.loads(m.group(1))
            if "tool" in obj:
                return obj
        except Exception:
            pass
    return None

# ----------------------------
# Routes: UI + meta + chat
# ----------------------------
@app.route("/", methods=["GET"])
def ui_home():
    # improved UI: shows project quick-buttons and tool-aware bubbles
    html = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Kust Bots — Support (Tool-enabled)</title>
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <style>
    :root{ --bg:#071033; --panel:#071a2b; --muted:#9fb0d6; --accent:#2563eb; --msg-user:#18314e; --msg-bot:#0b2a3c; --tool:#21412b; color-scheme:dark}
    body{margin:0;font-family:Inter,system-ui,Segoe UI,Roboto,Helvetica,Arial;background:linear-gradient(180deg,#020617 0%, #071033 100%);color:#e6eef8;height:100vh;display:flex;align-items:stretch}
    .sidebar{width:360px;background:var(--panel);padding:18px;box-sizing:border-box;border-right:1px solid rgba(255,255,255,0.03);display:flex;flex-direction:column;gap:10px}
    .brand{font-weight:700;font-size:18px}
    .desc{color:var(--muted);font-size:13px}
    .field{display:flex;flex-direction:column;gap:6px}
    .input{padding:10px;border-radius:8px;border:1px solid rgba(255,255,255,0.04);background:transparent;color:inherit}
    button{background:var(--accent);border:0;padding:10px 12px;border-radius:8px;color:white;cursor:pointer}
    .main{flex:1;display:flex;flex-direction:column;padding:18px;box-sizing:border-box}
    .top{display:flex;justify-content:space-between;align-items:center}
    .chat{margin-top:14px;background:rgba(255,255,255,0.01);border-radius:10px;padding:14px;flex:1;overflow:auto}
    .controls{display:flex;gap:10px;margin-top:12px}
    .msg{max-width:70%;padding:10px 12px;border-radius:10px;margin:8px 0;display:inline-block}
    .msg.user{background:var(--msg-user);margin-left:auto;text-align:right}
    .msg.bot{background:var(--msg-bot);text-align:left}
    .msg.tool{background:var(--tool);color:#e8ffe8;border-left:3px solid #5ec06a}
    .small{font-size:12px;color:var(--muted)}
    .projects{display:flex;gap:8px;flex-wrap:wrap;margin-top:6px}
    .pbtn{padding:6px 8px;border-radius:6px;background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.02);cursor:pointer}
    .meta{color:var(--muted);font-size:13px}
  </style>
</head>
<body>
  <div class="sidebar">
    <div class="brand">Kust Bots — Support</div>
    <div class="desc">Direct engineering-grade support. The assistant can request tool data about projects & commands automatically. Use the UI to chat, or click quick actions.</div>
    <div class="field">
      <label class="small">User ID</label>
      <input id="user" class="input" value="test_user" />
    </div>
    <div class="field">
      <label class="small">Quick actions</label>
      <div style="display:flex;gap:8px">
        <button id="btn-projects" class="pbtn">List Projects</button>
        <button id="btn-frozen" class="pbtn">Frozen Music</button>
        <button id="btn-commands" class="pbtn">Commands (frozen_music)</button>
      </div>
      <div class="projects" id="projects-div"></div>
    </div>
    <div style="margin-top:auto">
      <div class="meta">Model: <span id="model-name">loading...</span></div>
      <div class="meta">Env: <span id="env">checking...</span></div>
      <div style="height:8px"></div>
      <button id="reset">Reset Session</button>
    </div>
  </div>

  <div class="main">
    <div class="top">
      <div style="font-weight:700">Live Support Console</div>
      <div class="small" id="status">idle</div>
    </div>

    <div class="chat" id="chat"></div>

    <div class="controls">
      <input id="msg" class="input" placeholder="Ask about bots, paste logs, or press quick actions." />
      <button id="send">Send</button>
    </div>
    <div style="margin-top:8px"><span class="small">Tip: The assistant may respond with a tool request. The UI will show the tool output inline.</span></div>
  </div>

<script>
async function meta(){
  const res = await fetch('/meta'); const j = await res.json();
  document.getElementById('model-name').innerText = j.model || 'unknown';
  document.getElementById('env').innerText = j.ok ? 'ok' : 'missing';
}
meta();

function appendBubble(text, cls='bot'){
  const el = document.getElementById('chat');
  const d = document.createElement('div');
  d.className = 'msg ' + (cls==='user'?'user': (cls==='tool'?'tool':'bot'));
  d.innerText = text;
  el.appendChild(d); el.scrollTop = el.scrollHeight;
}

async function sendMessage(user, text){
  appendBubble(text, 'user');
  document.getElementById('status').innerText = 'sending...';
  try {
    const res = await fetch('/chat_tool', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({user, message: text})});
    const j = await res.json();
    if(j.error){ appendBubble('Error: ' + (j.details || j.error)); }
    else {
      // j may include tool events; server returns final 'response' and optional 'events' array for tool outputs
      if(j.events && Array.isArray(j.events)){
        for(const ev of j.events){
          if(ev.type==='tool_output') appendBubble('[Tool] ' + ev.data, 'tool');
          if(ev.type==='assistant_partial') appendBubble(ev.data, 'bot');
        }
      }
      if(j.response) appendBubble(j.response, 'bot');
    }
  } catch(e){
    appendBubble('Network error: ' + e);
  } finally {
    document.getElementById('status').innerText = 'idle';
  }
}

document.getElementById('send').addEventListener('click', ()=>{
  const u = document.getElementById('user').value.trim(); const m = document.getElementById('msg').value.trim();
  if(!u || !m) return alert('enter user and message');
  document.getElementById('msg').value='';
  sendMessage(u, m);
});
document.getElementById('msg').addEventListener('keydown', (e)=>{ if(e.key==='Enter') document.getElementById('send').click(); });
document.getElementById('reset').addEventListener('click', async ()=>{
  const u = document.getElementById('user').value.trim(); if(!u) return alert('enter user');
  await fetch('/reset', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({user:u})});
  document.getElementById('chat').innerHTML='';
  appendBubble('Session reset', 'bot');
});

document.getElementById('btn-projects').addEventListener('click', ()=> {
  const u = document.getElementById('user').value.trim(); sendMessage(u, "Please list all projects.");
});
document.getElementById('btn-frozen').addEventListener('click', ()=> {
  const u = document.getElementById('user').value.trim(); sendMessage(u, "Tell me about Frozen Music bot and how to use it.");
});
document.getElementById('btn-commands').addEventListener('click', ()=> {
  const u = document.getElementById('user').value.trim(); sendMessage(u, "Show me available commands for frozen_music.");
});
</script>
</body>
</html>
"""
    return render_template_string(html)

@app.route("/meta", methods=["GET"])
def meta():
    ok = bool(INFERENCE_KEY and INFERENCE_MODEL_ID and BASE_URL)
    return jsonify({"ok": ok, "model": INFERENCE_MODEL_ID or "unknown", "api_url": API_URL}), 200

@app.route("/reset", methods=["POST"])
def reset():
    data = request.json or {}
    user = data.get("user")
    if not user:
        return jsonify({"error": "missing user"}), 400
    CHAT_SESSIONS.pop(user, None)
    return jsonify({"ok": True}), 200

# ----------------------------
# Chat endpoint with tool-execution loop
# ----------------------------
@app.route("/chat_tool", methods=["POST"])
def chat_tool():
    """
    Expects JSON { "user": "<id>", "message": "..." }
    Returns JSON:
    {
      "response": "final assistant text",
      "events": [ {"type":"tool_output","data":"..."}, ... ]
    }
    """
    payload = request.json or {}
    user = payload.get("user")
    message = payload.get("message")
    if not user or not message:
        return jsonify({"error":"missing user or message"}), 400

    ensure_session(user)
    # append user message
    CHAT_SESSIONS[user].append({"role":"user", "content": message})

    events = []  # to send back tool outputs for UI display

    # We'll loop: call model, if it returns a tool-call JSON, execute tool and append tool output as system message and call again.
    MAX_ITER = 6
    for iteration in range(MAX_ITER):
        ok, assistant_content, raw = call_inference(CHAT_SESSIONS[user], timeout=60)
        if not ok:
            logger.warning("Inference failed: %s", assistant_content)
            # append assistant error to history so model sees it next time and we can retry later
            CHAT_SESSIONS[user].append({"role":"assistant", "content": f"[error] {assistant_content}"})
            return jsonify({"error":"inference_failed","details":assistant_content}), 502

        # Detect tool call JSON
        tool_req = parse_tool_call(assistant_content)
        if tool_req:
            # Append the assistant's tool call message into history (so conversation has record)
            CHAT_SESSIONS[user].append({"role":"assistant", "content": assistant_content})
            tool_name = tool_req.get("tool")
            tool_input = tool_req.get("input", {}) if isinstance(tool_req.get("input", {}), dict) else {}
            logger.info("Tool requested: %s (input=%s)", tool_name, tool_input)
            tool_func = TOOLS.get(tool_name)
            if not tool_func:
                tool_output = json.dumps({"error": f"tool '{tool_name}' not found"})
            else:
                try:
                    tool_output = tool_func(tool_input)
                except Exception as e:
                    logger.exception("tool execution error")
                    tool_output = json.dumps({"error": str(e)})
            # Append tool output as a system message so the model can consume it in the next turn
            tool_system_msg = {"role":"system", "content": f"[TOOL_OUTPUT] {tool_output}"}
            CHAT_SESSIONS[user].append(tool_system_msg)
            # Add an event for UI to display the tool output immediately
            events.append({"type":"tool_output", "data": tool_output})
            # continue loop to call model again with new context
            time.sleep(0.2)
            continue
        else:
            # No tool requested => final assistant reply. Append and return.
            CHAT_SESSIONS[user].append({"role":"assistant", "content": assistant_content})
            return jsonify({"response": assistant_content, "events": events}), 200

    # if reached here, too many iterations
    return jsonify({"error":"tool_loop_exceeded"}), 500

# ----------------------------
# Simple helper route to show raw KB (admin/debug)
# ----------------------------
@app.route("/_kb", methods=["GET"])
def show_kb():
    return jsonify(KB), 200

# ----------------------------
# Run (dev) — Heroku should use gunicorn; this allows local run
# ----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info("Starting Kust Support (tools) on port %d", port)
    app.run(host="0.0.0.0", port=port)
