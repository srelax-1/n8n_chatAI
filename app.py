from flask import Flask, request, jsonify, render_template
import csv
import docx
import requests
import re
import pdfplumber
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)

# n8n webhook endpoint 
N8N_WEBHOOK_URL = ""
N8N_UPLOAD_WEBHOOK = ""

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

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
            filename = secure_filename(file.filename)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)
            if os.path.getsize(filepath) == 0:
                return jsonify({"message": "Uploaded file is empty"}), 400

            # File type validation
            mimetype = file.mimetype
            if filename.lower().endswith(".pdf") and mimetype != "application/pdf":
                return jsonify({"message": "File extension is .pdf but mimetype is not PDF."}), 400
            if filename.lower().endswith(".csv") and mimetype not in ["text/csv", "application/vnd.ms-excel"]:
                return jsonify({"message": "File extension is .csv but mimetype is not CSV."}), 400
            if filename.lower().endswith(".docx") and mimetype != "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
                return jsonify({"message": "File extension is .docx but mimetype is not DOCX."}), 400
            
            # Determine file type:
            if filename.lower().endswith(".pdf"):
                chunks = chunk_pdf_with_pages(filepath)
            elif filename.lower().endswith(".csv"):
                chunks = chunk_csv_rows(filepath)
            elif filename.lower().endswith(".docx"):
                # Read DOCX and convert to text
                doc = docx.Document(filepath)
                text = "\n".join([para.text for para in doc.paragraphs])
                chunks = chunk_text(text)
            else:
                # Fallback for plain text or .txt files
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
                chunks = chunk_text(text)
            
            # Add source filename to all chunks
            for chunk in chunks:
                chunk["source_file"] = filename

            # Send chunks to n8n webhook
            res = requests.post(N8N_UPLOAD_WEBHOOK, json={"chunks": chunks})

            # Clean up uploaded file
            try:
                os.remove(filepath)
            except Exception as cleanup_err:
                # Optionally log cleanup_err or ignore
                pass
            
            if res.ok:
                return jsonify({"message": "File uploaded and sent to RAG workflow."})
            else:
                return jsonify({"message": "Upload failed: " + res.text}), 500
        except Exception as e:
            return jsonify({"message": f"Error: {str(e)}"}), 500
        
    return render_template("upload.html")


def chunk_pdf_with_pages(pdf_path, max_chars=1500):
    """
    Split PDF into page-based or paragraph-based chunks.
    """
    chunks = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            paragraphs = re.split(r'\n\s*\n', text)
            chunk_text = ""
            for para in paragraphs:
                if len(chunk_text) + len(para) > max_chars:
                    chunks.append({
                        "chunk_title": f"Page {page_num}",
                        "chunk_text": chunk_text.strip(),
                        "page_number": page_num
                    })
                    chunk_text = ""
                chunk_text += para + "\n\n"
            
            if chunk_text.strip():
                chunks.append({
                    "chunk_title": f"Page {page_num}",
                    "chunk_text": chunk_text.strip(),
                    "page_number": page_num
                })
    return chunks

def chunk_csv_rows(filepath, max_rows=50):
    """
    Chunk CSV file by rows. Each chunk contains up to max_rows rows.
    """
    chunks = []
    with open(filepath, newline='', encoding="utf-8", errors="ignore") as csvfile:
        reader = csv.reader(csvfile)
        header = next(reader, None)
        if not header:
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
        # Add any remaining rows
        if rows:
            chunk_text = "\n".join([", ".join(header)] + [", ".join(r) for r in rows])
            start = i - len(rows) + 1
            end = i
            chunks.append({
                "chunk_title": f"Rows {start}-{end}",
                "chunk_text": chunk_text
            })
    return chunks

def chunk_text(text, max_chars=1500):
    """
    Split plain text or Markdown by headings + paragraphs.
    """
    # Split into sections by Markdown-style headings
    sections = re.split(r'^(#{1,6}\s+.*)', text, flags=re.MULTILINE)
    
    chunks = []
    current_title = "Untitled Section"
    i = 0
    while i < len(sections):
        part = sections[i].strip()

        if re.match(r'^#{1,6}\s+', part):
            # It's a heading
            current_title = part.lstrip("# ").strip()
            i += 1
            continue
        
        if part:
            paragraphs = re.split(r'\n\s*\n', part)
            chunk_text = ""
            for para in paragraphs:
                if len(chunk_text) + len(para) > max_chars:
                    chunks.append({
                        "chunk_title": current_title,
                        "chunk_text": chunk_text.strip()
                    })
                    chunk_text = ""
                chunk_text += para + "\n\n"
            
            if chunk_text.strip():
                chunks.append({
                    "chunk_title": current_title,
                    "chunk_text": chunk_text.strip()
                })
        i += 1
    
    return chunks    

if __name__ == "__main__":
    app.run(debug=True, port=5000)