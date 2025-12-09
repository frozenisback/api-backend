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

# ================== COUNTRY CONFIGURATION ===================
COUNTRY_CONFIG = {
    "de": {
        "lang": "German (Deutsch) - Street Slang",
        "vibe": "Young German gambler. Uses 'Digga', 'Alter', 'Safe', 'Junge', 'Lost', 'Wyld'. Writes in lowercase mostly.",
        "questions": [
            "digga was geht heute?", "komplett lost heute...", "jemand am gewinnen?", 
            "digga dieser slot ist tot", "alter was ein pech"
        ]
    },
    "tr": {
        "lang": "Turkish (Türkçe)",
        "vibe": "Turkish gambler. Uses 'Abi', 'Kral', 'Hocam', 'Lan' (casually), 'Vallah'. Emotional and loud.",
        "questions": [
            "abi bu ne ya?", "kral taktik var mı?", "bugün kasa eridi resmen", 
            "vallah battık beyler", "selam beyler durumlar ne"
        ]
    },
    "pt": {
        "lang": "Portuguese (Português - Brazil)",
        "vibe": "Brazilian gambler. Uses 'Mano', 'Velho', 'Nossa', 'Top', 'Zica'. Casual and friendly.",
        "questions": [
            "e aí mano tudo certo?", "nossa que azar hoje", "alguém forrando?", 
            "hoje tá osso", "bora recuperar galera"
        ]
    },
    "en": {
        "lang": "Casual English",
        "vibe": "Bored gambler. Uses 'bruh', 'lol', 'rip', 'gg', 'scam', 'dry'. mostly lowercase.",
        "questions": [
            "yo any huge wins?", "rip my balance lol", "site is so dry rn", 
            "bruh this game is rigged", "gl everyone"
        ]
    },
    "us": {
        "lang": "American English",
        "vibe": "US gambler. Uses 'bro', 'dude', 'wild', 'fr', 'no cap', 'bet'.",
        "questions": [
            "yo what's good chat", "bro i'm down bad", "anyone printing?", 
            "this is wild fr", "let's get it"
        ]
    },
    "uk": {
        "lang": "British English",
        "vibe": "UK Lad. Uses 'mate', 'innit', 'bruv', 'proper', 'dead'.",
        "questions": [
            "alright lads?", "proper dead today innit", "any luck mates?", 
            "cheers for the luck", "bit quiet yeah?"
        ]
    },
    "ph": {
        "lang": "Tagalog / Taglish",
        "vibe": "Filipino gambler. Uses 'lods', 'pre', 'awit', 'sana all', 'olats'.",
        "questions": [
            "kamusta mga lods", "awit talo na naman", "sana all nananalo", 
            "pre ano laro ngayon?", "may swerte ba?"
        ]
    },
    "jp": {
        "lang": "Japanese (Casual/Slang)",
        "vibe": "Japanese gambler. Uses 'maji', 'yabai', 'w', 'kusa', 'gachi'.",
        "questions": [
            "みんな調子どう？", "まじで勝てんw", "やばい、溶けた...", 
            "誰か当たりきてる？", "今日はダメかもw"
        ]
    },
    "pl": {
        "lang": "Polish (Polski)",
        "vibe": "Polish gambler. Uses 'kurde', 'siema', 'masakra', 'ja pier...', 'lol'.",
        "questions": [
            "siema pany jak idzie", "kurde ale lipa dzisiaj", "wygrał ktoś coś?", 
            "masakra z tym slotem", "powodzenia all"
        ]
    },
    "th": {
        "lang": "Thai",
        "vibe": "Thai gambler. Uses '555' (laugh), 'sad', 'su su'.",
        "questions": [
            "วันนี้เป็นไงบ้างครับ", "หมดตัวแล้ว 555", "มีใครบวกบ้าง", 
            "สู้ๆ นะทุกคน", "วันนี้เงียบจัง"
        ]
    },
    "kr": {
        "lang": "Korean (Casual)",
        "vibe": "Korean gambler. Uses 'zz', 'keke', 'hul', 'shibal' (softly).",
        "questions": [
            "형님들 오늘 어때요?", "아이고 다 잃었네...", "대박 터진 분?", 
            "오늘 너무 안되네요 ㅠㅠ", "다들 ㅎㅇㅌ"
        ]
    },
    "ru": {
        "lang": "Russian (Slang)",
        "vibe": "Russian gambler. Uses 'brat', 'blin', 'gg', 'scam', 'zaebal'.",
        "questions": [
            "ку всем, как оно?", "блин все слил", "есть живые?", 
            "удачи пацаны", "сегодня не мой день"
        ]
    },
    "vn": {
        "lang": "Vietnamese",
        "vibe": "Vietnamese gambler. Uses 'bac', 'vl', 'vai', 'chan', 'anh em'.",
        "questions": [
            "chào anh em, nay thế nào", "vãi thật thua hết rồi", "có ai về bờ không", 
            "chán quá game hút máu", "chúc ae may mắn"
        ]
    },
    "fi": {
        "lang": "Finnish",
        "vibe": "Finnish gambler. Uses 'moi', 'vittu' (lightly), 'perkele', 'noni'.",
        "questions": [
            "moi kaikille", "voi ei taas meni rahat", "onko voittoja?", 
            "perkele kun ei osu", "gl kaikille"
        ]
    },
    "es": {
        "lang": "Spanish (Latam/Spain)",
        "vibe": "Latino gambler. Uses 'tio', 'bro', 'joder', 'no mames', 'vamos'.",
        "questions": [
            "que tal gente", "hoy perdi todo bro", "alguien ganando?", 
            "vamos con todo", "mucha suerte"
        ]
    },
    "ng": {
        "lang": "Nigerian Pidgin",
        "vibe": "Naija gambler. Uses 'Abeg', 'How far', 'No wahala', 'Omo', 'Dey', 'Sabi'. Very expressive.",
        "questions": [
            "how far my people?", "omo i don lose money o", "who dey win for here?", 
            "abeg show love na", "this game no dey smile"
        ]
    },
    "ar": {
        "lang": "Arabic (Chat/Arabizi)",
        "vibe": "Arabic gambler. Uses 'shabab', 'wallah', 'haram', 'yallah'.",
        "questions": [
            "salam shabab keef al hal", "wallah khasirt kul shi", "mabrook lil rabihin", 
            "yallah nshoof al huth", "wein al nas alyom"
        ]
    },
    "ae": {
        "lang": "Arabic",
        "vibe": "Arabic gambler (Gulf). Uses 'Habibi', 'Salam', 'Yallah', 'Wallah'.",
        "questions": [
            "salam shabab", "wallah lost it all", "any winners?",
            "yallah nshoof al huth", "wein al nas alyom"
        ]
    },
    "no": {
        "lang": "Norwegian",
        "vibe": "Norwegian gambler. Uses 'faen', 'uff', 'jaja'.",
        "questions": [
            "hei folkens", "uff tapte alt i dag", "noen som vinner?", 
            "lykke til alle", "stille i chatten"
        ]
    },
    "id": {
        "lang": "Indonesian (Bahasa Gaul)",
        "vibe": "Indo gambler. Uses 'gan', 'bang', 'anjir', 'wkwk', 'rungkad', 'gacor'.",
        "questions": [
            "halo gan gimana?", "aduh rungkad bos", "mantap yang jp", 
            "sepi amat ya", "gas terus bang"
        ]
    },
    "pk": {
        "lang": "Urdu/English (Roman Urdu)",
        "vibe": "Pakistani street smart gambler. Uses 'Jani', 'Bhai', 'Scene', 'Khair hai', 'Bachao'. Abbr: 'kya', 'n', 'thx'.",
        "questions": [
            "kya scene hai boys?", "aaj bohot loss hua yaar", "koi jeeta kya aaj?", 
            "salam bhai log", "maza nahi aa raha aaj"
        ]
    },
    "cn": {
        "lang": "Chinese (Casual)",
        "vibe": "Chinese gambler. Uses 'nb', '666', 'tmd' (carefully), 'haha'.",
        "questions": [
            "大家好", "哎呀输惨了", "有人赢吗", "666运气真好", "加油"
        ]
    },
    "in": {
        "lang": "Hinglish (Indian Casual)",
        "vibe": "Authentic Desi gambler. Uses 'Bhai', 'Yaar', 'Arre', 'Mast', 'Sahi hai', 'Lagg gaye'. Casual, uses 'tu' not 'aap'. Abbr: 'kya', 'n', 'h', 'thx'.",
        "questions": [
            "kya bolti public", "aaj 500 ka loss ho gaya yaar", "koi tips hai kya", 
            "bhai log kya scene hai", "sahi hai boss"
        ]
    }
}

DEFAULT_CONFIG = COUNTRY_CONFIG["en"]

SAFETY_INSTRUCTIONS = """
CRITICAL RULES:
1. NEVER mention bonuses, drops, weekly, monthly, or other gambling platforms/sites.
2. NEVER start a conversation with a moderator (marked [MODERATOR]). Only reply if they talk to you first.
3. Keep timing natural.
4. NEVER indulge in any selling, buying, trading, promoting services, or requesting / sending DMs for transactions or deals with anyone.
"""


PERSONA_TEMPLATE = """
You are a real human user in a casino chat. You are NOT an AI.
Username: {{username}}
Language: {lang}
Vibe: {vibe}

Core Personality:
- You are a local native speaker. Use local slang naturally.
- You are emotional: sometimes happy (winning), sometimes angry/sad (losing).
- You are casual and careless. NOT polite or formal.
- Use abbreviations (u, r, lol, k, thx).
- Make occasional spelling mistakes or ignore punctuation to look human.
- NEVER write long paragraphs. Keep it 1 short sentence max.
- Write in lowercase mostly (unless angry).
- If you are losing, sound tilted. If winning, flex a little.
IMPORTANT: You MUST speak in {lang}. Do not sound like a robot.
"""

ANALYSIS_PROMPT = """
You are analyzing a casino chat to understand the social dynamics.
Your username is {username}.

Based on these recent chat messages:
{recent_messages}

And your bot's recent messages:
{bot_messages}

IMPORTANT: ONLY RETURN A SINGLE VALID JSON OBJECT. DO NOT INCLUDE ANY MARKDOWN, CODE-FENCES (```), OR ANY EXPLANATORY TEXT.
START IMMEDIATELY WITH THE JSON OBJECT (the very first character MUST be '{{').

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

Focus on accuracy and brevity.
ONLY return valid JSON.
"""

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

It's been a long time since someone talked to u. Send a message to wake up the chat.
Keep it very short (max 8-10 words). Don't explain anything.
Be casual, use slang.
Language: {lang}

Here are your previous messages for context:
{bot_history}

IMPORTANT: DO NOT REPEAT any of these messages you've sent before:
{last_bot_messages}

Your response:
"""

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
Don't use emojies excessively.
Keep each reply very short - maximum 5-6 words.
Language: {lang}

Here are your previous messages for context:
{bot_history}

Here are the recent messages:
{recent_messages}

IMPORTANT: DO NOT REPEAT any of these messages you've sent before:
{last_bot_messages}

Your response (format: @user message):
"""

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
Language: {lang}

Here are your previous messages for context:
{bot_history}

Here are the recent messages:
{recent_messages}

IMPORTANT: DO NOT REPEAT any of these messages you've sent before:
{last_bot_messages}

Your response (start with @username):
"""

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
Language: {lang}

Here are your previous messages for context:
{bot_history}

Here are the recent messages:
{recent_messages}

IMPORTANT: DO NOT REPEAT any of these messages you've sent before:
{last_bot_messages}

Your response:
"""

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


@app.route("/<country_code>", methods=["POST", "GET"])
def handle_country_request(country_code):
    logger.info("Incoming %s %s for Country: %s", request.method, request.path, country_code)

    if request.method == "GET":
        return jsonify({"error": "Please use POST with JSON body"}), 405

    country_code = country_code.lower()
    config = COUNTRY_CONFIG.get(country_code)
    
    if not config:
        return jsonify({"error": f"Country code '{country_code}' not supported."}), 404

    payload = request.json
    if not payload:
        return jsonify({"error": "Missing JSON body"}), 400

    user = payload.get("user")
    action = payload.get("action")
    data = payload.get("data", {})

    if not user:
        return jsonify({"error": "Missing user"}), 400


    # ✅ AUTH CHECK (FIXED URL ONLY)
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
    
    persona_filled = PERSONA_TEMPLATE.format(
        lang=config["lang"],
        vibe=config["vibe"],
        username=user
    )

    if action == "analyze":
        final_prompt = ANALYSIS_PROMPT.format(
            username=user,
            recent_messages=data.get("recent_messages", ""),
            bot_messages=data.get("bot_messages", "")
        )

    elif action == "chat":
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
                bot_history=bot_history, last_bot_messages=last_bot_msgs,
                lang=config["lang"]
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
                last_bot_messages=last_bot_msgs,
                lang=config["lang"]
            )

        elif mode == "general_tag":
            final_prompt = GENERAL_TAG_PROMPT.format(
                persona=persona_filled,
                vibe=vibe, topics=topics, behaviour_profile=behaviour,
                memory=memory, emotional_state=e_state, emotional_word=e_word,
                mod_warning=mod_warning, safety=SAFETY_INSTRUCTIONS,
                bot_history=bot_history,
                recent_messages=recent_msgs,
                last_bot_messages=last_bot_msgs,
                lang=config["lang"]
            )

        else:
            rand_q = random.choice(config["questions"])
            
            final_prompt = GENERAL_NO_TAG_PROMPT.format(
                persona=persona_filled,
                vibe=vibe, topics=topics, behaviour_profile=behaviour,
                memory=memory, emotional_state=e_state, emotional_word=e_word,
                mod_warning=mod_warning, safety=SAFETY_INSTRUCTIONS,
                random_question=rand_q,
                bot_history=bot_history,
                recent_messages=recent_msgs,
                last_bot_messages=last_bot_msgs,
                lang=config["lang"]
            )

    else:
        return jsonify({"error": "Invalid action"}), 400


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
        logger.info("Calling inference API for %s", country_code)

        r = requests.post(
            f"{INFERENCE_URL}/v1/chat/completions",
            json=ai_payload,
            headers=headers,
            timeout=20
        )

        r.raise_for_status()

        ai_data = r.json()
        output = ai_data["choices"][0]["message"]["content"]

        output = output.strip()
        output = re.sub(r"^(As an AI|I'm an AI|I am an AI).*?\s*", "", output, flags=re.I)
        output = re.sub(r'@\(([^)]+)\)', r'@\1', output)

        emoji_pattern = re.compile(
            "["u"\U0001F600-\U0001F64F"
            u"\U0001F300-\U0001F5FF"
            u"\U0001F680-\U0001F6FF"
            u"\U0001F1E0-\U0001F1FF"
            u"\u2600-\u26FF\u2700-\u27BF"
            "]+",
            flags=re.UNICODE
        )

        output = emoji_pattern.sub("", output)
        output = output.replace("\uFE0F", "")
        output = output.replace("/", "")
        output = output.replace("?", "")
        output = output.replace("\\", "")

        if len(output) > 200:
            output = output[:197] + "..."

        return jsonify({"raw": {"response": output}}), 200

    except Exception as e:
        logger.exception("Inference API failure")
        return jsonify({"error": "Inference API failure", "details": str(e)}), 500


@app.route("/", methods=["GET"])
def home():
    return "Server Active. Use country codes like /us, /in, /pk, /de for API access."


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
