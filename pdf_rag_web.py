"""
PDF RAG 웹 서버
- PDF 업로드 → ChromaDB 벡터 저장
- 웹에서 질문 → 관련 내용 검색 → Ollama LLM 답변
"""

import os
import hashlib
import time
from flask import Flask, request, jsonify, render_template
from pdf_rag import (
    add_pdf, get_collection, chunk_text, extract_text_from_pdf,
    OLLAMA_URL, CHAT_MODEL, TOP_K,
)
import requests

app = Flask(__name__)
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.route("/")
def index():
    return render_template("pdf_rag.html")


@app.route("/api/upload", methods=["POST"])
def upload_pdf():
    """PDF 파일 업로드 및 벡터 DB 등록"""
    if "file" not in request.files:
        return jsonify({"error": "파일이 없습니다"}), 400

    file = request.files["file"]
    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "PDF 파일만 업로드 가능합니다"}), 400

    # 파일명이 너무 길면 해시로 축약
    original_name = file.filename
    if len(original_name.encode('utf-8')) > 200:
        ext = os.path.splitext(original_name)[1]
        short = original_name[:50] + "_" + hashlib.md5(original_name.encode()).hexdigest()[:8] + ext
        safe_name = short
    else:
        safe_name = original_name

    filepath = os.path.join(UPLOAD_DIR, safe_name)
    file.save(filepath)

    try:
        add_pdf(filepath)
        return jsonify({"message": f"{original_name} 등록 완료"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/ask", methods=["POST"])
def ask_question():
    """질문에 대해 PDF 내용 기반 답변"""
    data = request.get_json()
    question = data.get("question", "").strip()
    if not question:
        return jsonify({"error": "질문을 입력하세요"}), 400

    collection = get_collection()
    if collection.count() == 0:
        return jsonify({"error": "등록된 PDF가 없습니다. 먼저 PDF를 업로드하세요."})

    # 벡터 검색
    results = collection.query(query_texts=[question], n_results=TOP_K)
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    sources = []
    for doc, meta, dist in zip(documents, metadatas, distances):
        sources.append({
            "source": meta["source"],
            "similarity": round(1 - dist, 2),
            "text": doc[:200],
        })

    # LLM 답변 생성
    context = "\n\n---\n\n".join(
        f"[출처: {m['source']}]\n{d}" for d, m in zip(documents, metadatas)
    )
    prompt = f"""아래 참고 문서를 바탕으로 질문에 답변하세요.
참고 문서에 없는 내용은 "문서에 해당 내용이 없습니다"라고 답하세요.

## 참고 문서
{context}

## 질문
{question}

## 답변"""

    resp = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={"model": CHAT_MODEL, "prompt": prompt, "stream": False},
        timeout=120,
    )
    resp.raise_for_status()
    answer = resp.json()["response"].strip()

    return jsonify({"answer": answer, "sources": sources})


@app.route("/api/docs", methods=["GET"])
def list_documents():
    """등록된 문서 목록"""
    collection = get_collection()
    count = collection.count()
    if count == 0:
        return jsonify({"docs": [], "total_chunks": 0})

    all_data = collection.get()
    doc_map = {}
    for meta in all_data["metadatas"]:
        src = meta["source"]
        doc_map[src] = doc_map.get(src, 0) + 1

    docs = [{"name": name, "chunks": cnt} for name, cnt in sorted(doc_map.items())]
    return jsonify({"docs": docs, "total_chunks": count})


@app.route("/api/delete", methods=["POST"])
def delete_document():
    """등록된 문서 삭제"""
    data = request.get_json()
    name = data.get("name", "")
    if not name:
        return jsonify({"error": "문서 이름이 필요합니다"}), 400

    collection = get_collection()
    existing = collection.get(where={"source": name})
    if not existing["ids"]:
        return jsonify({"error": "해당 문서를 찾을 수 없습니다"}), 404

    collection.delete(ids=existing["ids"])
    return jsonify({"message": f"{name} 삭제 완료"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
