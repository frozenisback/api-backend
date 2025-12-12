import os
import requests
import time
from flask import Flask, Response

app = Flask(__name__)

# -------------------------------
# LOAD CREDS FROM HEROKU ENV
# -------------------------------
API_URL = os.getenv("INFERENCE_URL")  # e.g. https://xxx.inference.run
INFERENCE_KEY = os.getenv("INFERENCE_KEY")
MODEL_NAME = os.getenv("INFERENCE_MODEL_ID")

HEADERS = {
    "Authorization": f"Bearer {INFERENCE_KEY}",
    "Content-Type": "application/json"
}

# -------------------------------


def test_prompt(token_len: int):
    """Send a test request with a prompt containing token_len words."""
    prompt = "word " * token_len

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }

    try:
        r = requests.post(API_URL, json=payload, headers=HEADERS, timeout=12)
        if r.status_code == 200:
            return True
        return False
    except Exception:
        return False


def sse(msg):
    return f"data: {msg}\n\n"


@app.route("/api")
def run_test():
    def stream():
        yield sse("🔥 Starting token limit detection...")

        test_steps = [100, 300, 500, 800]
        last_success = 0
        last_fail = None

        # ---------------------------
        # PHASE 1: COARSE CHECK
        # ---------------------------
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
            yield sse("⚠ No failure detected up to 800 tokens.")
            yield sse("📌 Increase test range manually if needed.")
            return

        # ------------------------------------
        # PHASE 2: BINARY SEARCH FOR HARD LIMIT
        # ------------------------------------
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

        final_limit = low
        yield sse(f"🎉 FINAL MAX INPUT TOKEN LIMIT: {final_limit}")

    return Response(stream(), mimetype="text/event-stream")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
