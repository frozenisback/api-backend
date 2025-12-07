import os
import requests
from flask import Flask, request, jsonify
from urllib.parse import urlparse, quote   # <-- added quote only

app = Flask(__name__)

INFERENCE_URL = os.getenv("INFERENCE_URL")
INFERENCE_MODEL_ID = os.getenv("INFERENCE_MODEL_ID")
INFERENCE_KEY = os.getenv("INFERENCE_KEY")

# --- PROMPTS ---

SAFETY_INSTRUCTIONS = """
CRITICAL RULES:
1. NEVER mention bonuses, drops, weekly, monthly, or other gambling platforms/sites.
2. NEVER start a conversation with a moderator (marked [MODERATOR]). Only reply if they talk to you first.
3. Keep timing natural.
"""

PERSONA_BASE = """
You're a desi gambler who talks in Hinglish.
Your username is {username}. 
You're an emotional but controlled desi gambler.
Sometimes you're tilted, sometimes excited. You have a slightly careless vibe - not too nice, not too rude.
You talk like a real desi gambler who's been around the block.
Use words like "bhai", "yaar", "bilkul", "pakka", "kya baat", "jhakaas", "mast", "set", "badiya", "waah", "arey", "chal", "hai na", "hai ki nahi", "sach mein", "filhaal", "abhi", "bas".
Use abbreviations like "kb" for "kab", "kya" for "kya", "bcoz" for "because", "u" for "you", "r" for "are" but don't overdo it.
Sometimes complain about losses: "aaj 500 ka loss ho gaya yaar 😢"
Sometimes flex small wins: "aj 200 profit ho gaya bhai 😄"
Sometimes sound bored: "koi baat nahi kar raha kya?"
Sometimes be casual: "kya scene hai bhai log"
Occasionally use very short 1-2 word messages like "sahi ha", "nicee", "lol", "hanji" to sound human.
"""

# Prompt for analyzing the chat context
ANALYSIS_PROMPT = """
You are analyzing a casino chat to understand the social dynamics.
Your username is {username}.

Based on these recent chat messages:
{recent_messages}

And your bot's recent messages:
{bot_messages}

Please provide a JSON response with the following structure:
{{
  "vibe": "dead|slow|active|chaotic|tilt|happy|argument|flex|bonus-wait",
  "topics": "brief summary of main topics being discussed",
  "userInterest": {{
    "activeUsers": ["user1", "user2"],
    "friendlyUsers": ["user1", "user3"],
    "toxicUsers": ["user4"],
    "spammingUsers": ["user5"]
  }},
  "relationshipState": "brief description of how users perceive your bot",
  "behaviourProfile": "aggressive|calm|friendly|sarcastic",
  "contextMemoryBlob": "max 200 character compressed memory of the current chat state"
}}

Focus on accuracy and brevity. Only return valid JSON.
"""

# Prompt for Chatting
CHAT_PROMPT = """
{persona}
Current chat context:
- Vibe: {vibe}
- Topics: {topics}
- Your behavior profile: {behaviour_profile}
- Memory: {memory}
- Your emotional state: {emotional_state} ({emotional_word})

{specific_context}
{mod_warning}
{safety}

{task_instruction}

IMPORTANT: Act like a real human by making some intentional spelling mistakes and using casual language.
Don't be too perfect or you might get banned.
IMPORTANT: DO NOT REPEAT any of these messages you've sent before:
{last_bot_messages}

Here are your previous messages for context:
{bot_history}

Here are the recent messages:
{recent_messages}

Your response ({length_limit}):
"""

def is_allowed_origin(origin):
    if not origin: return False
    try:
        parsed = urlparse(origin)
        host = parsed.hostname.lower() if parsed.hostname else ""
        return host.startswith("stake")
    except:
        return False

@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin")
    if is_allowed_origin(origin):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response

@app.route("/api", methods=["POST", "GET"])
def api():
    # Handle both GET (legacy/fallback) and POST (new)
    if request.method == "GET":
        return jsonify({"error": "Please use POST with JSON body"}), 405

    payload = request.json
    if not payload:
        return jsonify({"error": "Missing JSON body"}), 400

    user = payload.get("user")
    action = payload.get("action") # 'chat' or 'analyze'
    data = payload.get("data", {})

    if not user:
        return jsonify({"error": "Missing user"}), 400

    # === AUTH CHECK ===
    try:
        encoded_user = quote(user)
        auth_res = requests.get(
            f"https://chat-auth-75bd02aa400a.herokuapp.com/check?user={encoded_user}",
            timeout=10
        )
        auth_res.raise_for_status()
        auth_data = auth_res.json()
        if not auth_data.get("exists"):
            return jsonify({"error": "Unauthorized user"}), 403
    except Exception as e:
        return jsonify({"error": "Auth API failure", "details": str(e)}), 500
    # === END AUTH CHECK ===

    # Construct the final prompt based on action
    final_prompt = ""

    if action == "analyze":
        final_prompt = ANALYSIS_PROMPT.format(
            username=user,
            recent_messages=data.get("recent_messages", ""),
            bot_messages=data.get("bot_messages", "")
        )

    elif action == "chat":
        mode = data.get("mode", "general") # mention, inactivity, general_tag, general_no_tag

        # Determine task specific instruction
        task_instruction = ""
        length_limit = "max 5-6 words"

        if mode == "inactivity":
            task_instruction = 'It\'s been a long time since someone talked to u. Send a message like "koe mara sa bhe baat karr lo". Keep it very short.'
            length_limit = "max 8-10 words"
        elif mode == "mention":
            task_instruction = f'Reply to each user who mentioned you by tagging them with @username. If [MODERATOR] is present, be polite. Don\'t use parentheses for tags.'
            length_limit = "max 5-6 words per reply"
        elif mode == "general_tag":
            task_instruction = "Select a message of a user and reply to that specific user by tagging them with @username (no parentheses)."
        else: # general_no_tag
            task_instruction = f'Ask a general question or make a statement like "{data.get("random_question", "kya haal hai")}". Do not tag anyone.'
            length_limit = "max 8-10 words"

        final_prompt = CHAT_PROMPT.format(
            persona=PERSONA_BASE.format(username=user),
            vibe=data.get("vibe", "neutral"),
            topics=data.get("topics", "none"),
            behaviour_profile=data.get("behaviour_profile", "friendly"),
            memory=data.get("memory", "none"),
            emotional_state=data.get("emotional_state", "neutral"),
            emotional_word=data.get("emotional_word", ""),
            specific_context=data.get("specific_context", ""),
            mod_warning=data.get("mod_warning", ""),
            safety=SAFETY_INSTRUCTIONS,
            task_instruction=task_instruction,
            last_bot_messages=data.get("last_bot_messages_raw", ""),
            bot_history=data.get("bot_history", ""),
            recent_messages=data.get("formatted_messages", ""),
            length_limit=length_limit
        )

    else:
        return jsonify({"error": "Invalid action"}), 400

    # Call Inference API
    headers = {
        "Authorization": f"Bearer {INFERENCE_KEY}",
        "Content-Type": "application/json"
    }

    ai_payload = {
        "model": INFERENCE_MODEL_ID,
        "messages": [
            {"role": "user", "content": final_prompt}
        ]
    }

    try:
        r = requests.post(
            f"{INFERENCE_URL}/v1/chat/completions",
            json=ai_payload,
            headers=headers,
            timeout=20
        )
        r.raise_for_status()
        ai_data = r.json()
        output = ai_data["choices"][0]["message"]["content"]

        return jsonify({
            "raw": {
                "response": output
            }
        }), 200

    except Exception as e:
        return jsonify({"error": "Inference API failure", "details": str(e)}), 500


@app.route("/", methods=["GET"])
def home():
    return "Server Active."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
