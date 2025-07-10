from flask import Flask, request, jsonify, render_template
import csv
import docx
import requests
import re
import pdfplumber
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
N8N_BASIC_AUTH_USER = os.getenv('N8N_BASIC_AUTH_USER')
N8N_BASIC_AUTH_PASSWORD = os.getenv('N8N_BASIC_AUTH_PASSWORD')

auth = (N8N_BASIC_AUTH_USER, N8N_BASIC_AUTH_PASSWORD)

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
        
        response = requests.post(N8N_CHAT_WEBHOOK, json=user_input, auth=auth)
        logger.info(f"n8n chat response status: {response.status_code}")
        logger.debug(f"n8n chat response content: {response.text}")
        
        return jsonify(response.json())
    except Exception as e:
        logger.exception("Error in /chat route")
        return jsonify({"aiResponse": f"⚠️ Error: {str(e)}"}), 500

@app.route("/upload", methods=["GET", "POST"])
def upload_file():
    if request.method == "POST":
        logger.info("POST request received at /upload")
        if "file" not in request.files:
            logger.warning("No file part in request")
            return jsonify({"message": "No file part in request"}), 400

        file = request.files["file"]
        logger.info(f"Received file: {file.filename}")
        
        if file.filename == "":
            logger.warning("No file selected")
            return jsonify({"message": "No file selected"}), 400

        try:
            filename = secure_filename(file.filename)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            logger.info(f"Saving file to: {filepath}")
            
            file.save(filepath)
            
            file_size = os.path.getsize(filepath)
            logger.info(f"File saved. Size: {file_size} bytes")
            
            if file_size == 0:
                logger.warning("Uploaded file is empty")
                return jsonify({"message": "Uploaded file is empty"}), 400
            
            # if file_size > 50 * 1024 * 1024:  # 50 MB limit
            #     logger.error("Uploaded file exceeds size limit of 10 MB")
            #     return jsonify({"message": "Uploaded file exceeds size limit of 10 MB"}), 413

            # Process file
            if filename.lower().endswith(".pdf"):
                chunks = chunk_pdf_with_pages(filepath)
            elif filename.lower().endswith(".csv"):
                chunks = chunk_csv_rows(filepath)
            elif filename.lower().endswith(".docx"):
                doc = docx.Document(filepath)
                text = "\n".join([para.text for para in doc.paragraphs])
                chunks = chunk_text(text)
            else:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
                chunks = chunk_text(text)

            logger.info(f"File processed into {len(chunks)} chunks.")

            # Add source file info
            for chunk in chunks:
                chunk["source_file"] = filename

            # Send chunks to n8n
            logger.info(f"Sending chunks to N8N_UPLOAD_WEBHOOK: {N8N_UPLOAD_WEBHOOK}")
            res = requests.post(N8N_UPLOAD_WEBHOOK, json={"chunks": chunks}, auth=auth)
            
            if res.ok:
                logger.info("Upload to n8n successful.")
                response_message = "File uploaded and sent to RAG workflow."
            else:
                logger.error(f"Upload to n8n failed: {res.status_code} - {res.text}")
                return jsonify({"message": "Upload failed: " + res.text}), 500

            # Clean up the uploaded file after processing
            try:
                os.remove(filepath)
                logger.info(f"Removed file: {filepath}")
            except Exception as cleanup_err:
                logger.warning(f"Failed to remove file {filepath}: {cleanup_err}")

            return jsonify({"message": response_message})

        except Exception as e:
            logger.exception("Error processing upload")
            return jsonify({"message": f"Error: {str(e)}"}), 500

    # GET method
    logger.info("Rendering upload page")
    return render_template("upload.html")


def chunk_pdf_with_pages(pdf_path, max_chars=1500):
    logger.info(f"Chunking PDF file: {pdf_path}")
    chunks = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            paragraphs = re.split(r'\n\s*\n', text)
            chunk_text_accum = ""
            for para in paragraphs:
                if len(chunk_text_accum) + len(para) > max_chars:
                    chunks.append({
                        "chunk_title": f"Page {page_num}",
                        "chunk_text": chunk_text_accum.strip(),
                        "page_number": page_num
                    })
                    chunk_text_accum = ""
                chunk_text_accum += para + "\n\n"
            if chunk_text_accum.strip():
                chunks.append({
                    "chunk_title": f"Page {page_num}",
                    "chunk_text": chunk_text_accum.strip(),
                    "page_number": page_num
                })
    logger.info(f"Created {len(chunks)} chunks from PDF.")
    return chunks

def chunk_csv_rows(filepath, max_rows=50):
    logger.info(f"Chunking CSV file: {filepath}")
    chunks = []
    with open(filepath, newline='', encoding="utf-8", errors="ignore") as csvfile:
        reader = csv.reader(csvfile)
        header = next(reader, None)
        if not header:
            logger.warning("CSV file has no header row.")
            return []
        rows = []
        i = 0
        for i, row in enumerate(reader, 1):
            rows.append(row)
            if i % max_rows == 0:
                chunk_text = "\n".join([", ".join(header)] + [", ".join(r) for r in rows])
                chunks.append({
                    "chunk_title": f"Rows {i - len(rows) + 1}-{i}",
                    "chunk_text": chunk_text
                })
                rows = []
        if rows:
            chunk_text = "\n".join([", ".join(header)] + [", ".join(r) for r in rows])
            start = i - len(rows) + 1
            end = i
            chunks.append({
                "chunk_title": f"Rows {start}-{end}",
                "chunk_text": chunk_text
            })
    logger.info(f"Created {len(chunks)} chunks from CSV.")
    return chunks

def chunk_text(text, max_chars=1500):
    logger.info(f"Chunking plain text.")
    sections = re.split(r'^(#{1,6}\s+.*)', text, flags=re.MULTILINE)
    
    chunks = []
    current_title = "Untitled Section"
    i = 0
    while i < len(sections):
        part = sections[i].strip()

        if re.match(r'^#{1,6}\s+', part):
            current_title = part.lstrip("# ").strip()
            i += 1
            continue
        
        if part:
            paragraphs = re.split(r'\n\s*\n', part)
            chunk_text_accum = ""
            for para in paragraphs:
                if len(chunk_text_accum) + len(para) > max_chars:
                    chunks.append({
                        "chunk_title": current_title,
                        "chunk_text": chunk_text_accum.strip()
                    })
                    chunk_text_accum = ""
                chunk_text_accum += para + "\n\n"
            
            if chunk_text_accum.strip():
                chunks.append({
                    "chunk_title": current_title,
                    "chunk_text": chunk_text_accum.strip()
                })
        i += 1
    
    logger.info(f"Created {len(chunks)} chunks from text.")
    return chunks


if __name__ == "__main__":
    logger.info("Starting Flask app...")
    app.run(debug=False, port=5000)