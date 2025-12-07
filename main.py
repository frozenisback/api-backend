import os
import random
import requests
from flask import Flask, request, jsonify
from urllib.parse import urlparse, quote

app = Flask(__name__)

INFERENCE_URL = os.getenv("INFERENCE_URL")
INFERENCE_MODEL_ID = os.getenv("INFERENCE_MODEL_ID")
INFERENCE_KEY = os.getenv("INFERENCE_KEY")

# --- PROMPTS & PERSONA ---

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

# 1. Context Analysis Prompt
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

# 2. Inactivity Prompt
INACTIVITY_PROMPT = """
{persona}
Current chat context:
- Vibe: {vibe}
- Topics: {topics}
- Your behavior profile: {behaviour_profile}
- Memory: {memory}
- Your emotional state: {emotional_state} ({emotional_word})
{mod_warning}
{safety}

It's been a long time since someone talked to u. Send a message like "koe mara sa bhe baat karr lo". 
Keep it very short (max 8-10 words). Don't explain anything.

Here are your previous messages for context:
{bot_history}

IMPORTANT: DO NOT REPEAT any of these messages you've sent before:
{last_bot_messages}

Your response:
"""

# 3. Mention/Reply Prompt
MENTION_PROMPT = """
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

Reply to each user who mentioned you by tagging them with @username. 
If [MODERATOR] is present, be polite.
IMPORTANT: Use @username format WITHOUT parentheses. For example: @Sudhirrps not @(Sudhirrps).
Act like a real human by making some intentional spelling mistakes and using casual language.
Don't use emojies.
Keep each reply very short - maximum 5-6 words.

Here are your previous messages for context:
{bot_history}

Here are the recent messages:
{recent_messages}

IMPORTANT: DO NOT REPEAT any of these messages you've sent before:
{last_bot_messages}

Your response (format: @user message):
"""

# 4. General Tag Prompt (Proactive tagging)
GENERAL_TAG_PROMPT = """
{persona}
Current chat context:
- Vibe: {vibe}
- Topics: {topics}
- Your behavior profile: {behaviour_profile}
- Memory: {memory}
- Your emotional state: {emotional_state} ({emotional_word})
{mod_warning}
{safety}

Select a message of a user and reply to that specific user by tagging them with @username (no parentheses).
Based on these chat messages, respond with something VERY SHORT - maximum 5-6 words only. Don't explain anything.
Act like a real human by making some intentional spelling mistakes and using casual language.

Here are your previous messages for context:
{bot_history}

Here are the recent messages:
{recent_messages}

IMPORTANT: DO NOT REPEAT any of these messages you've sent before:
{last_bot_messages}

Your response (start with @username):
"""

# 5. General No-Tag Prompt (General Chat)
GENERAL_NO_TAG_PROMPT = """
{persona}
Current chat context:
- Vibe: {vibe}
- Topics: {topics}
- Your behavior profile: {behaviour_profile}
- Memory: {memory}
- Your emotional state: {emotional_state} ({emotional_word})
{mod_warning}
{safety}

Ask a general question or make a statement like "{random_question}". 
Do not tag anyone.
Keep it short (max 8-10 words).
Act like a real human by making some intentional spelling mistakes.

Here are your previous messages for context:
{bot_history}

Here are the recent messages:
{recent_messages}

IMPORTANT: DO NOT REPEAT any of these messages you've sent before:
{last_bot_messages}

Your response:
"""

# General Questions List (Moved from Client)
GENERAL_QUESTIONS = [
    "aaj kafi loss ho gya yaar 😢",
    "aaj 150 usd ka profit hua 😄",
    "koi hai jo aaj jackpot jeeta?",
    "kya lag raha hai aaj ka match?",
    "kya strategy use kar rahe ho aaj?",
    "kya baat hai bhai log kaise ho?",
    "aaj ka mood kaisa hai sabka?",
    "kya chal raha hai chat me?",
    "kya khabar hai dosto?",
    "kya scene hai aaj ka?",
    "kya plan hai aaj ke liye?",
    "kya lagta hai aaj lucky rahega?",
    "koi tips hai aaj ke liye?",
    "kya baat hai sab silent kyun?",
    "aaj ka kya target hai sabka?",
    "koi haal chaal batao bhai log",
    "kya scene hai bhai log?",
    "aaj kya special hai bhai?"
]

def is_allowed_origin(origin):
    if not origin:
        return False
    if origin.startswith("chrome-extension://"):
        return True
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
        # Using the exact auth URL from your client code
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

    final_prompt = ""
    system_instruction = "You are a helpful AI assistant." # Default

    if action == "analyze":
        final_prompt = ANALYSIS_PROMPT.format(
            username=user,
            recent_messages=data.get("recent_messages", ""),
            bot_messages=data.get("bot_messages", "")
        )

    elif action == "chat":
        mode = data.get("mode", "general_no_tag")
        
        # Common data for all chat prompts
        persona_filled = PERSONA_BASE.format(username=user)
        vibe = data.get("vibe", "neutral")
        topics = data.get("topics", "none")
        behaviour = data.get("behaviour_profile", "friendly")
        memory = data.get("memory", "none")
        e_state = data.get("emotional_state", "neutral")
        e_word = data.get("emotional_word", "")
        mod_warning = data.get("mod_warning", "")
        bot_history = data.get("bot_history", "")
        last_bot_msgs = data.get("last_bot_messages_raw", "")
        recent_msgs = data.get("formatted_messages", "")
        
        if mode == "inactivity":
            final_prompt = INACTIVITY_PROMPT.format(
                persona=persona_filled,
                vibe=vibe, topics=topics, behaviour_profile=behaviour,
                memory=memory, emotional_state=e_state, emotional_word=e_word,
                mod_warning=mod_warning, safety=SAFETY_INSTRUCTIONS,
                bot_history=bot_history, last_bot_messages=last_bot_msgs
            )
            
        elif mode == "mention":
            specific_context = data.get("specific_context", "")
            final_prompt = MENTION_PROMPT.format(
                persona=persona_filled,
                vibe=vibe, topics=topics, behaviour_profile=behaviour,
                memory=memory, emotional_state=e_state, emotional_word=e_word,
                specific_context=specific_context, mod_warning=mod_warning, 
                safety=SAFETY_INSTRUCTIONS, bot_history=bot_history,
                recent_messages=recent_msgs, last_bot_messages=last_bot_msgs
            )
            
        elif mode == "general_tag":
            final_prompt = GENERAL_TAG_PROMPT.format(
                persona=persona_filled,
                vibe=vibe, topics=topics, behaviour_profile=behaviour,
                memory=memory, emotional_state=e_state, emotional_word=e_word,
                mod_warning=mod_warning, safety=SAFETY_INSTRUCTIONS,
                bot_history=bot_history, recent_messages=recent_msgs,
                last_bot_messages=last_bot_msgs
            )
            
        else: # general_no_tag
            random_q = random.choice(GENERAL_QUESTIONS)
            final_prompt = GENERAL_NO_TAG_PROMPT.format(
                persona=persona_filled,
                vibe=vibe, topics=topics, behaviour_profile=behaviour,
                memory=memory, emotional_state=e_state, emotional_word=e_word,
                mod_warning=mod_warning, safety=SAFETY_INSTRUCTIONS,
                random_question=random_q, bot_history=bot_history,
                recent_messages=recent_msgs, last_bot_messages=last_bot_msgs
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
        
        # --- SERVER SIDE CLEANING ---
        output = output.strip()
        # Remove AI disclaimers
        output = output.replace("As an AI", "").replace("I'm an AI", "").replace("I am an AI", "")
        # Fix Tagging format: @(User) -> @User
        import re
        output = re.sub(r'@\(([^)]+)\)', r'@\1', output)
        
        # Hard truncate if too long (safety net)
        if len(output) > 200:
            output = output[:197] + "..."

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
