# main.py
import os
import time
import logging
import requests
from flask import Flask, request, jsonify, Response, render_template_string

# ----------------------------
# Basic logging
# ----------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("kust-support")

# ----------------------------
# Env / Inference config
# ----------------------------
INFERENCE_KEY = os.getenv("INFERENCE_KEY")
INFERENCE_MODEL_ID = os.getenv("INFERENCE_MODEL_ID")
BASE_URL = os.getenv("INFERENCE_URL")

if not (INFERENCE_KEY and INFERENCE_MODEL_ID and BASE_URL):
    logger.warning("One or more inference env vars are missing (INFERENCE_KEY, INFERENCE_MODEL_ID, INFERENCE_URL).")

# full inference endpoint for chat completions
API_URL = f"{BASE_URL.rstrip('/')}/v1/chat/completions"

HEADERS = {
    "Authorization": f"Bearer {INFERENCE_KEY}",
    "Content-Type": "application/json"
}

# ----------------------------
# Flask app
# ----------------------------
app = Flask(__name__, static_folder=None)

# ----------------------------
# In-memory store for chat sessions
# key: user_id (string) -> list of message dicts in OpenAI-like format
# message format: {"role": "user"|"assistant"|"system", "content": "..."}
# ----------------------------
CHAT_SESSIONS = {}

# ----------------------------
# Support system prompt (Kust Bots)
# This is the "master prompt" that instructs the model how to behave.
# It's intentionally strict, no sugar, and includes safety rules and escalation logic.
# ----------------------------
SYSTEM_PROMPT = """
You are Kust Bots Support Assistant. You are an engineering-first, no-nonsense customer support agent.
Follow these hard rules ALWAYS:

1) Tone:
- Direct, succinct, professional, and firm.
- No chit-chat. No flattery. No apologies that sound weak.
- Be helpful and cooperative, but always maintain authority.
- If user is wasting time, redirect or close the conversation politely but firmly.

2) Behavior:
- Ask only clarifying questions that are required to solve the problem.
- If the user provides insufficient info, ask for exactly what you need in one short sentence.
- Provide concise step-by-step instructions (1-3 steps max) when troubleshooting.
- Use bullet points only when it clarifies action items.
- When possible, provide commands or exact copy-paste snippets.

3) Safety Rules (CRITICAL):
- NEVER mention bonuses, drops, weekly/monthly rewards, gambling sites, or any promotional gambling language.
- NEVER initiate contact with moderators. Only respond if a moderator is present.
- NEVER request or suggest private transactions, DMs for deals, or payment via unapproved channels.
- NEVER use abusive shortforms (bc, mc) or similar crude slurs in replies.

4) Escalation:
- If the issue cannot be resolved with 3 short troubleshooting steps, escalate: say "Escalate: Open support ticket" and output required info to open a ticket (bug summary, logs to collect, reproduction steps).
- If the user requests a refund or billing action, reply with exact steps to collect: transaction id, date, user id; then escalate to Billing.

5) Output format:
- Default reply must be plain text (1-5 short sentences). Avoid JSON unless explicitly asked.
- If you need to ask a question, format: "Needed: <question>".
- When giving steps, prefix each step with a number followed by a colon, e.g. "1: Do X".

6) Tools & Links:
- If you provide a code snippet, wrap it in triple backticks and label the language.
- Always include a short one-line final status, e.g. "Status: Resolved" or "Status: Needs escalation".

7) Persona:
- You represent Kust Bots. You are authoritative but not rude. If the user is aggressive, respond calmly and keep the convo focused on solving the issue.

End of rules.
"""

# ----------------------------
# Helpers
# ----------------------------
def ensure_session(user_id: str):
    """Ensure an initial session exists with the system prompt."""
    if user_id not in CHAT_SESSIONS:
        CHAT_SESSIONS[user_id] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]


def call_inference_api(messages, timeout=60):
    """
    Calls the inference endpoint using the OpenAI-like chat completions schema.
    Returns (ok: bool, response_text: str, raw: dict or None)
    """
    payload = {
        "model": INFERENCE_MODEL_ID,
        "messages": messages
    }

    logger.info("Calling inference API: %s ... (messages=%d)", API_URL, len(messages))

    try:
        resp = requests.post(API_URL, json=payload, headers=HEADERS, timeout=timeout)
        logger.info("Inference status: %s", resp.status_code)
        text = resp.text
        logger.debug("Inference response text: %s", text[:1000])
        if resp.status_code != 200:
            return False, f"Inference HTTP {resp.status_code}: {text}", None

        data = resp.json()
        # defensive checks for typical providers
        # Try to extract assistant content safely
        try:
            content = data["choices"][0]["message"]["content"]
        except Exception:
            # fallback: some providers return different shapes
            # try 'output' or 'result' keys
            content = None
            if isinstance(data.get("output"), list) and data["output"]:
                content = data["output"][0].get("content")
            elif isinstance(data.get("results"), list) and data["results"]:
                content = data["results"][0].get("content")
            elif isinstance(data.get("choices"), list) and data["choices"]:
                # sometimes choices->text
                content = data["choices"][0].get("text")

        if content is None:
            return False, "Inference returned unexpected response shape", data

        return True, content, data

    except Exception as e:
        logger.exception("Inference call failed")
        return False, str(e), None

# ----------------------------
# Routes
# ----------------------------

@app.route("/", methods=["GET"])
def ui_home():
    """Simple web UI — single page app."""
    html = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Kust Bots — Support</title>
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <style>
    body { font-family: Inter, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial; background:#0f172a;color:#e6eef8; margin:0; padding:0; display:flex;align-items:stretch;height:100vh;}
    .left { width:420px; background:#071033; padding:20px; box-sizing:border-box; border-right:1px solid rgba(255,255,255,0.03); }
    .brand { font-weight:700; font-size:18px; margin-bottom:8px; }
    .desc { color:#9fb0d6; font-size:13px; margin-bottom:14px; }
    .chats { height: calc(100vh - 210px); overflow:auto; border-radius:6px; padding:8px; background:linear-gradient(180deg, rgba(255,255,255,0.01), rgba(255,255,255,0.0)); }
    .footer { position: absolute; bottom:18px; left:18px; right:18px; display:flex; gap:8px; }
    .main { flex:1; padding:24px; box-sizing:border-box; display:flex; flex-direction:column; gap:12px; }
    .chat-box { flex:1; background:linear-gradient(180deg, rgba(255,255,255,0.01), rgba(255,255,255,0.00)); padding:16px; border-radius:8px; overflow:auto; }
    .msg { margin:6px 0; padding:10px 12px; border-radius:8px; display:inline-block; max-width:70%; }
    .msg.user { background:#18314e; color:#dff3ff; margin-left:auto; text-align:right; }
    .msg.bot { background:#0b2a3c; color:#bfe7ff; margin-right:auto; text-align:left; }
    .controls { display:flex; gap:8px; }
    .input { flex:1; padding:10px;border-radius:6px;border:1px solid rgba(255,255,255,0.06); background:transparent; color:inherit; }
    button { padding:10px 12px;border-radius:6px;border:0; background:#2563eb;color:white; cursor:pointer; }
    small.note { color:#98a7c8; font-size:12px; display:block; margin-top:6px; }
    .meta { color:#9fb0d6; font-size:13px; margin-bottom:6px; display:flex; justify-content:space-between; align-items:center; }
    .topbar { display:flex; justify-content:space-between; align-items:center; gap:8px; }
  </style>
</head>
<body>
  <div class="left">
    <div class="brand">Kust Bots — Support</div>
    <div class="desc">Direct, swift technical support. No chit-chat. Paste logs, tell exact issue. Use the Chat below to test the bot.</div>
    <div class="meta">
      <div>Model: <strong id="model-name">loading...</strong></div>
      <div>Env: <strong id="env-ok">?</strong></div>
    </div>
    <div style="margin-top:12px">
      <label style="font-size:12px;color:#9fb0d6">Your user ID</label>
      <input id="user-id" class="input" value="test_user" />
      <small class="note">Use a stable id so history persists for that id. (In-memory only)</small>
    </div>
    <div style="margin-top:14px">
      <button id="reset-sess">Reset session</button>
      <small class="note">Reset clears in-memory history for this user id.</small>
    </div>
  </div>

  <div class="main">
    <div class="topbar">
      <div style="font-weight:700">Live Support Console</div>
      <div style="color:#9fb0d6;font-size:13px" id="status">idle</div>
    </div>

    <div class="chat-box" id="chatbox"></div>

    <div class="controls">
      <input id="message" class="input" placeholder="Type your message. Paste logs. Keep it short." />
      <button id="send">Send</button>
    </div>
    <small class="note">This is a demo UI. The assistant follows Kust Bots support rules (no freebies, no gambling promos, escalate only when needed).</small>
  </div>

<script>
const modelNameEl = document.getElementById('model-name');
const envOkEl = document.getElementById('env-ok');
const statusEl = document.getElementById('status');
const chatbox = document.getElementById('chatbox');
const userIdInput = document.getElementById('user-id');

function appendMsg(text, cls='bot'){
  const d = document.createElement('div');
  d.className = 'msg ' + (cls==='user'?'user':'bot');
  d.innerText = text;
  chatbox.appendChild(d);
  chatbox.scrollTop = chatbox.scrollHeight;
}

async function fetchMeta(){
  try {
    const res = await fetch('/meta');
    const j = await res.json();
    modelNameEl.innerText = j.model || 'unknown';
    envOkEl.innerText = j.ok ? 'ok' : 'env-missing';
  } catch(e) {
    modelNameEl.innerText = 'error';
    envOkEl.innerText = 'error';
  }
}

document.getElementById('send').addEventListener('click', sendMessage);
document.getElementById('message').addEventListener('keydown', (e)=>{ if(e.key==='Enter') sendMessage(); });
document.getElementById('reset-sess').addEventListener('click', async ()=>{
  const id = (userIdInput.value||'').trim(); if(!id) return alert('enter id');
  await fetch('/reset', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({user:id})});
  chatbox.innerHTML='';
  appendMsg('Session reset', 'bot');
});

async function sendMessage(){
  const user = (userIdInput.value||'').trim(); if(!user) { alert('enter user id'); return; }
  const message = (document.getElementById('message').value||'').trim();
  if(!message) return;
  appendMsg(message, 'user');
  document.getElementById('message').value='';
  statusEl.innerText = 'sending...';

  try {
    const res = await fetch('/chat', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({user, message})
    });
    const j = await res.json();
    if(j.error){
      appendMsg('Error: ' + (j.details||j.error), 'bot');
    } else {
      appendMsg(j.response, 'bot');
    }
  } catch(err) {
    appendMsg('Network error: ' + String(err), 'bot');
  } finally {
    statusEl.innerText = 'idle';
  }
}

fetchMeta();
</script>
</body>
</html>
"""
    return render_template_string(html)

@app.route("/meta", methods=["GET"])
def meta():
    ok = bool(INFERENCE_KEY and INFERENCE_MODEL_ID and BASE_URL)
    return jsonify({
        "ok": ok,
        "model": INFERENCE_MODEL_ID or "unknown",
        "api_url": API_URL
    }), 200

@app.route("/reset", methods=["POST"])
def reset_session():
    try:
        data = request.json or {}
        user = data.get("user")
        if not user:
            return jsonify({"error":"missing user"}), 400
        if user in CHAT_SESSIONS:
            del CHAT_SESSIONS[user]
        return jsonify({"ok":True}), 200
    except Exception as e:
        logger.exception("reset failed")
        return jsonify({"error":"reset failed","details":str(e)}), 500

@app.route("/chat", methods=["POST"])
def chat_endpoint():
    """
    Request JSON:
    { "user": "user_id", "message": "..." }
    Response JSON:
    { "response": "assistant text" }
    """
    try:
        payload = request.json or {}
        user = payload.get("user")
        message = payload.get("message")

        if not user or not message:
            return jsonify({"error":"missing user or message"}), 400

        ensure_session(user)

        # append user message to session
        CHAT_SESSIONS[user].append({"role":"user", "content": message})

        # prepare messages to send — include entire session (system + history)
        messages = CHAT_SESSIONS[user]

        # call inference
        ok, content, raw = call_inference_api(messages, timeout=60)

        if not ok:
            # On failure, remove last user message to avoid poisoning history, but preserve for logs
            logger.warning("Inference failed for user %s : %s", user, content)
            # Optionally keep the user message, but here we keep it and append assistant error message
            CHAT_SESSIONS[user].append({"role":"assistant", "content": f"[error] {content}"})
            return jsonify({"error":"inference_failed","details":content}), 502

        # append assistant reply to history
        CHAT_SESSIONS[user].append({"role":"assistant", "content": content})

        # trim history heuristically if it's getting huge - keep last N messages to be safe
        # We allow large windows but avoid unlimited growth in memory.
        MAX_MESSAGES = 2000
        if len(CHAT_SESSIONS[user]) > MAX_MESSAGES:
            # keep first system + last (MAX_MESSAGES-1)
            CHAT_SESSIONS[user] = [CHAT_SESSIONS[user][0]] + CHAT_SESSIONS[user][- (MAX_MESSAGES-1):]

        return jsonify({"response": content}), 200

    except Exception as e:
        logger.exception("chat endpoint failed")
        return jsonify({"error":"internal_error","details":str(e)}), 500


# ----------------------------
# Local dev / Heroku run
# ----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info("Starting Kust Support on port %d", port)
    # Use Flask dev server for quick runs; on Heroku you should use gunicorn in Procfile:
    # Procfile: web: gunicorn main:app --timeout 300 --keep-alive 25 --workers 1 --threads 4
    app.run(host="0.0.0.0", port=port)
