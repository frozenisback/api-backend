import os
import requests
import time
from flask import Flask, Response

app = Flask(__name__)

# -------------------------------
# ENV LOADING
# -------------------------------
BASE_URL = os.getenv("INFERENCE_URL")
API_URL = f"{BASE_URL}/v1/chat/completions"

HEADERS = {
    "Authorization": f"Bearer {INFERENCE_KEY}",
    "Content-Type": "application/json"
}

INFERENCE_KEY = os.getenv("INFERENCE_KEY")
MODEL_NAME = os.getenv("INFERENCE_MODEL_ID")



# -------------------------------
# SSE FORMATTER + LOGGING
# -------------------------------
def sse(msg):
    print("SSE →", msg)  # prints to heroku logs
    return f"data: {msg}\n\n"


# -------------------------------
# TEST FUNCTION WITH LOGGING
# -------------------------------
def test_prompt(token_len: int):
    prompt = "word " * token_len

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }

    print("====================================")
    print(f"TESTING TOKEN LENGTH → {token_len}")
    print("URL:", API_URL)
    print("PAYLOAD:", payload)
    print("HEADERS:", HEADERS)

    try:
        r = requests.post(API_URL, json=payload, headers=HEADERS, timeout=12)

        print("STATUS:", r.status_code)
        print("RESPONSE:", r.text)

        if r.status_code == 200:
            return True

        return False

    except Exception as e:
        print("REQUEST ERROR:", e)
        return False


# -------------------------------
# SSE ENDPOINT
# -------------------------------
@app.route("/api")
def run_test():
    def stream():
        yield sse("🔥 Starting token limit detection...")

        test_steps = [100, 300, 500, 800]
        last_success = 0
        last_fail = None

        # COARSE TEST
        for size in test_steps:
            yield sse(f"⏳ Testing {size} tokens...")
            ok = test_prompt(size)

            if ok:
                yield sse(f"✔ PASSED at {size}")
                last_success = size
            else:
                yield sse(f"❌ FAILED at {size}")
                last_fail = size
                break

            time.sleep(0.1)

        if last_fail is None:
            yield sse("⚠ No failure up to 800. Increase test range manually.")
            return

        # BINARY SEARCH
        low = last_success
        high = last_fail
        yield sse(f"🔍 Narrowing range from {low} → {high}...")

        while high - low > 5:
            mid = (low + high) // 2
            yield sse(f"⏳ Testing {mid} tokens...")

            ok = test_prompt(mid)

            if ok:
                yield sse(f"✔ PASSED at {mid}")
                low = mid
            else:
                yield sse(f"❌ FAILED at {mid}")
                high = mid

            time.sleep(0.1)

        yield sse(f"🎉 FINAL MAX INPUT TOKEN LIMIT: {low}")

    return Response(stream(), mimetype="text/event-stream")


# -------------------------------
# LOCAL DEV ONLY (Heroku won't use this)
# -------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
