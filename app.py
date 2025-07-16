from flask import Flask, request, jsonify, render_template
import requests
import os
import logging
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("app.log", mode="a", encoding="utf-8"),
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Environment Variables
N8N_CHAT_WEBHOOK = os.getenv('N8N_CHAT_WEBHOOK')
N8N_UPLOAD_WEBHOOK = os.getenv('N8N_UPLOAD_WEBHOOK')

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@app.route("/")
def index():
    logger.info("Rendering index page")
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    try:
        user_input = request.get_json()
        logger.info(f"Received /chat request: {user_input}")
        
        response = requests.post(N8N_CHAT_WEBHOOK, json=user_input)
        logger.info(f"n8n chat response status: {response.status_code}")
        logger.debug(f"n8n chat response content: {response.text}")
        
        return jsonify(response.json())
    except Exception as e:
        logger.exception("Error in /chat route")
        return jsonify({"aiResponse": f"⚠️ Error: {str(e)}"}), 500


@app.route("/upload", methods=["GET", "POST"])
def upload_file():
    if request.method == "GET":
        logger.info("Rendering upload page")
        return render_template("upload.html")
    
    if "file" not in request.files:
        return jsonify({"message": "No file part in request"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"message": "No file selected"}), 400

    files = {
        "file": (file.filename, file.stream, file.mimetype)
    }

    res = requests.post(
        N8N_UPLOAD_WEBHOOK,
        files=files
    )

    if res.ok:
        return jsonify({"message": "File uploaded and forwarded to n8n workflow."})
    else:
        return jsonify({"message": f"Upload failed: {res.text}"}), 500

if __name__ == "__main__":
    logger.info("Starting Flask app...")
    app.run(debug=False, port=5000)