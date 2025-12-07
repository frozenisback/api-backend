import os
import random
import requests
import logging
import json
import re
from flask import Flask, request, jsonify
from urllib.parse import urlparse, quote

# ================== LOGGING ===================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("CHAT-FARMER")
# ==============================================

app = Flask(__name__)

INFERENCE_URL = os.getenv("INFERENCE_URL")
INFERENCE_MODEL_ID = os.getenv("INFERENCE_MODEL_ID")
INFERENCE_KEY = os.getenv("INFERENCE_KEY")

logger.info("Inference URL: %s", INFERENCE_URL)
logger.info("Inference MODEL: %s", INFERENCE_MODEL_ID)
logger.info("Inference KEY set: %s", bool(INFERENCE_KEY))


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

IMPORTANT: ONLY RETURN A SINGLE VALID JSON OBJECT. DO NOT INCLUDE ANY MARKDOWN, CODE-FENCES (```), OR ANY EXPLANATORY TEXT. START IMMEDIATELY WITH THE JSON OBJECT (i.e. the very first character output MUST be '{').

Your JSON must match this structure exactly:
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

Focus on accuracy and brevity. Only return valid JSON with no surrounding text.
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

# 4. General Tag Prompt
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

# 5. General No-Tag Prompt
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

# ✅ RESTORED — Fixes NameError crash
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
    "kya baat hai sab silent kyu?",
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


def _clean_json_like_text(text: str) -> str:
    """
    Cleans model output to extract a direct JSON object string.
    - Removes triple/backtick fences and any leading/trailing non-json text.
    - Extracts the first balanced {...} JSON object while being careful about strings and escapes.
    - If no balanced object is found, returns trimmed (fence-stripped) text.
    """
    if not isinstance(text, str):
        return text

    s = text.strip()

    # Remove common code fences (```json or ```)
    s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*```$", "", s, flags=re.IGNORECASE)
    # Remove single backticks
    s = s.replace("`", "")

    # If the cleaned text already starts with '{' try to extract the balanced object
    first_brace = s.find('{')
    if first_brace == -1:
        return s.strip()

    i = first_brace
    brace_count = 0
    in_string = False
    escape = False
    end_index = None

    while i < len(s):
        ch = s[i]

        if ch == '"' and not escape:
            in_string = not in_string
        if ch == '\\' and not escape:
            escape = True
            i += 1
            continue
        else:
            escape = False

        if not in_string:
            if ch == '{':
                brace_count += 1
            elif ch == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_index = i
                    break
        i += 1

    if end_index is not None:
        candidate = s[first_brace:end_index + 1].strip()
        # Final safety: try to load as JSON to ensure validity
        try:
            json.loads(candidate)
            return candidate
        except Exception:
            # if parsing fails, fall through to return candidate anyway
            return candidate

    # Fallback: return the fence-stripped trimmed string
    return s.strip()


@app.route("/api", methods=["POST", "GET"])
def api():
    logger.info("Incoming %s %s", request.method, request.path)

    if request.method == "GET":
        return jsonify({"error": "Please use POST with JSON body"}), 405

    payload = request.json
    if not payload:
        return jsonify({"error": "Missing JSON body"}), 400

    user = payload.get("user")
    action = payload.get("action")
    data = payload.get("data", {})

    if not user:
        return jsonify({"error": "Missing user"}), 400

    # ✅ FIXED AUTH (adds @ if missing)
    try:
        if not user.startswith("@"):
            user = "@" + user

        encoded_user = quote(user)
        auth_url = f"https://chat-auth-75bd02aa400a.herokuapp.com/check?user={encoded_user}"
        logger.info("Auth check: %s", auth_url)

        auth_res = requests.get(auth_url, timeout=10)
        auth_res.raise_for_status()

        auth_data = auth_res.json()
        logger.info("Auth response: %s", auth_data)

        if not auth_data.get("exists"):
            return jsonify({"error": "Unauthorized user"}), 403

    except Exception as e:
        logger.exception("Auth API failure")
        return jsonify({"error": "Auth API failure", "details": str(e)}), 500


    final_prompt = ""

    if action == "analyze":
        final_prompt = ANALYSIS_PROMPT.format(
            username=user,
            recent_messages=data.get("recent_messages", ""),
            bot_messages=data.get("bot_messages", "")
        )

    elif action == "chat":
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

        mode = data.get("mode", "general_no_tag")

        if mode == "inactivity":
            final_prompt = INACTIVITY_PROMPT.format(
                persona=persona_filled,
                vibe=vibe, topics=topics, behaviour_profile=behaviour,
                memory=memory, emotional_state=e_state, emotional_word=e_word,
                mod_warning=mod_warning, safety=SAFETY_INSTRUCTIONS,
                bot_history=bot_history, last_bot_messages=last_bot_msgs
            )

        elif mode == "mention":
            final_prompt = MENTION_PROMPT.format(
                persona=persona_filled,
                vibe=vibe, topics=topics, behaviour_profile=behaviour,
                memory=memory, emotional_state=e_state, emotional_word=e_word,
                specific_context=data.get("specific_context", ""),
                mod_warning=mod_warning, safety=SAFETY_INSTRUCTIONS,
                bot_history=bot_history,
                recent_messages=recent_msgs,
                last_bot_messages=last_bot_msgs
            )

        elif mode == "general_tag":
            final_prompt = GENERAL_TAG_PROMPT.format(
                persona=persona_filled,
                vibe=vibe, topics=topics, behaviour_profile=behaviour,
                memory=memory, emotional_state=e_state, emotional_word=e_word,
                mod_warning=mod_warning, safety=SAFETY_INSTRUCTIONS,
                bot_history=bot_history,
                recent_messages=recent_msgs,
                last_bot_messages=last_bot_msgs
            )

        else:
            final_prompt = GENERAL_NO_TAG_PROMPT.format(
                persona=persona_filled,
                vibe=vibe, topics=topics, behaviour_profile=behaviour,
                memory=memory, emotional_state=e_state, emotional_word=e_word,
                mod_warning=mod_warning, safety=SAFETY_INSTRUCTIONS,
                random_question=random.choice(GENERAL_QUESTIONS),
                bot_history=bot_history,
                recent_messages=recent_msgs,
                last_bot_messages=last_bot_msgs
            )

    else:
        return jsonify({"error": "Invalid action"}), 400


    # === INFERENCE CALL ===
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
        logger.info("Calling inference API")

        r = requests.post(
            f"{INFERENCE_URL}/v1/chat/completions",
            json=ai_payload,
            headers=headers,
            timeout=20
        )

        r.raise_for_status()

        ai_data = r.json()
        output = ai_data["choices"][0]["message"]["content"]

        # Basic clean: remove common AI disclaimers if present
        output = output.strip()
        output = re.sub(r"^(As an AI[, ]*.*?\.?\s*)", "", output, flags=re.IGNORECASE)
        output = re.sub(r"^(I am an AI[, ]*.*?\.?\s*)", "", output, flags=re.IGNORECASE)
        output = re.sub(r"^(I'm an AI[, ]*.*?\.?\s*)", "", output, flags=re.IGNORECASE)

        # Replace odd parentheses-mention patterns like @(... ) -> @...
        output = re.sub(r'@\(([^)]+)\)', r'@\1', output)

        # Clean fences and try to extract a direct JSON object if this was an analyze action.
        if action == "analyze":
            cleaned = _clean_json_like_text(output)
            # If cleaned text does not start with '{', as a last resort, keep original stripped text.
            if cleaned and cleaned[0] == '{':
                output = cleaned
            else:
                # still try to return cleaned text (best-effort)
                output = cleaned

            # IMPORTANT: do NOT truncate analysis outputs — they must be valid JSON and not cut off.
        else:
            # For chat responses, we may keep shorter responses to fit UI. Truncate if very long.
            if len(output) > 200:
                output = output[:197] + "..."

        return jsonify({"raw": {"response": output}}), 200

    except Exception as e:
        logger.exception("Inference API failure")
        return jsonify({"error": "Inference API failure", "details": str(e)}), 500


@app.route("/", methods=["GET"])
def home():
    return "Server Active."


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
