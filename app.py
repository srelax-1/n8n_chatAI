from flask import Flask, request, jsonify, render_template
import requests

app = Flask(__name__)

# Your n8n webhook endpoint (local or ngrok)
N8N_WEBHOOK_URL = ""
N8N_UPLOAD_WEBHOOK = ""

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
    

@app.route("/upload", methods=["GET", "POST"])
def upload_file():
    if request.method == "POST":
        if "file" not in request.files:
            return jsonify({"message": "No file part in request"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"message": "No file selected"}), 400

        try:
            # Send file to n8n RAG workflow webhook
            files = { "file": (file.filename, file.stream, file.mimetype) }
            res = requests.post(N8N_UPLOAD_WEBHOOK, files=files)

            if res.ok:
                return jsonify({"message": "File uploaded and sent to RAG workflow."})
            else:
                return jsonify({"message": "Upload failed: " + res.text}), 500
        except Exception as e:
            return jsonify({"message": f"Error: {str(e)}"}), 500

    return render_template("upload.html")

if __name__ == "__main__":
    app.run(debug=True, port=5000)