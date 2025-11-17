import os
import requests
from flask import Flask, request, jsonify, make_response
from urllib.parse import urlparse

app = Flask(__name__)

INFERENCE_URL = os.getenv("INFERENCE_URL")
INFERENCE_MODEL_ID = os.getenv("INFERENCE_MODEL_ID")
INFERENCE_KEY = os.getenv("INFERENCE_KEY")


def is_allowed_origin(origin):
    if not origin:
        return False

    try:
        parsed = urlparse(origin)
        host = parsed.hostname.lower() if parsed.hostname else ""
    except:
        return False

    if not host:
        return False

    # Allow stake.<anything>
    if host.startswith("stake."):
        return True

    # Allow stake-<anything>
    if host.startswith("stake-"):
        return True

    return False


@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin")
    if is_allowed_origin(origin):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    return response


@app.route("/api", methods=["GET"])
def api():
    q = request.args.get("q")

    if not q:
        return jsonify({"error": "Missing q"}), 400

    # Prepare request to Heroku Inference API
    headers = {
        "Authorization": f"Bearer {INFERENCE_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "modelId": INFERENCE_MODEL_ID,
        "input": q
    }

    try:
        r = requests.post(
            INFERENCE_URL,
            json=payload,
            headers=headers,
            timeout=20
        )
        r.raise_for_status()
    except Exception as e:
        return jsonify({"error": "Inference API failure", "details": str(e)}), 500

    data = r.json()

    # Extract response safely
    output = (
        data.get("output") or
        data.get("result") or
        data.get("response") or
        data
    )

    return make_response(str(output), 200)


@app.route("/", methods=["GET"])
def home():
    return "Heroku AI API is running."


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
