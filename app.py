from flask import Flask, request, jsonify, render_template
import requests

app = Flask(__name__)

# Your n8n webhook endpoint (local or ngrok)
N8N_WEBHOOK_URL = "your webhook URL here"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    try:
        user_input = request.get_json()
        response = requests.post(N8N_WEBHOOK_URL, json=user_input)
        return jsonify(response.json())
    except Exception as e:
        return jsonify({"aiResponse": f"⚠️ Error: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)