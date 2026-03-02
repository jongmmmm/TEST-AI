"""
PDF RAG (Retrieval-Augmented Generation) 시스템
- PDF 파일을 읽어서 ChromaDB에 벡터 저장
- 질문하면 관련 내용을 검색하여 Ollama LLM으로 답변 생성
"""

import os
import sys
import argparse
import hashlib

import chromadb
from chromadb.utils import embedding_functions
import requests
from pypdf import PdfReader


# ── 설정 ──────────────────────────────────────────────
OLLAMA_URL = "http://192.168.0.13:11434"
EMBED_MODEL = "nomic-embed-text"   # Ollama 임베딩 모델
CHAT_MODEL = "gpt-oss"             # Ollama 채팅 모델
CHROMA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db")
COLLECTION_NAME = "pdf_docs"
CHUNK_SIZE = 500       # 글자 수 기준
CHUNK_OVERLAP = 100    # 겹치는 글자 수
TOP_K = 5              # 검색 결과 수


# ── Ollama 임베딩 함수 (ChromaDB용) ───────────────────
class OllamaEmbeddingFunction:
    """ChromaDB에서 사용할 Ollama 임베딩 함수"""

    def __init__(self, url: str, model: str):
        self.url = url
        self.model = model

    def name(self) -> str:
        return "ollama_embed"

    def _get_embeddings(self, texts: list[str]) -> list[list[float]]:
        embeddings = []
        for text in texts:
            resp = requests.post(
                f"{self.url}/api/embed",
                json={"model": self.model, "input": text},
            )
            resp.raise_for_status()
            embeddings.append(resp.json()["embeddings"][0])
        return embeddings

    def __call__(self, input: list[str]) -> list[list[float]]:
        return self._get_embeddings(input)

    def embed_documents(self, input: list[str]) -> list[list[float]]:
        return self._get_embeddings(input)

    def embed_query(self, input: list[str]) -> list[list[float]]:
        return self._get_embeddings(input)


# ── PDF 텍스트 추출 ───────────────────────────────────
def extract_text_from_pdf(pdf_path: str) -> str:
    """PDF 파일에서 텍스트 추출"""
    reader = PdfReader(pdf_path)
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        if text:
            pages.append(f"[페이지 {i + 1}]\n{text}")
    return "\n\n".join(pages)


# ── 텍스트 청킹 ──────────────────────────────────────
def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """텍스트를 겹치는 청크로 분할"""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start += chunk_size - overlap
    return chunks


# ── ChromaDB 클라이언트 ──────────────────────────────
def get_collection():
    """ChromaDB 컬렉션 반환"""
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    embed_fn = OllamaEmbeddingFunction(url=OLLAMA_URL, model=EMBED_MODEL)
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embed_fn,
        metadata={"hnsw:space": "cosine"},
    )
    return collection


# ── PDF 등록 ─────────────────────────────────────────
def add_pdf(pdf_path: str):
    """PDF를 읽어서 ChromaDB에 저장"""
    if not os.path.exists(pdf_path):
        print(f"[오류] 파일을 찾을 수 없습니다: {pdf_path}")
        return

    filename = os.path.basename(pdf_path)
    print(f"PDF 읽는 중: {filename}")

    text = extract_text_from_pdf(pdf_path)
    if not text.strip():
        print("[오류] PDF에서 텍스트를 추출할 수 없습니다.")
        return

    chunks = chunk_text(text)
    print(f"  텍스트 추출 완료: {len(text)}자 → {len(chunks)}개 청크")

    collection = get_collection()

    # 파일별 고유 ID 생성
    file_hash = hashlib.md5(pdf_path.encode()).hexdigest()[:8]
    ids = [f"{file_hash}_{i}" for i in range(len(chunks))]
    metadatas = [{"source": filename, "chunk_index": i} for i in range(len(chunks))]

    # 기존 동일 파일 데이터 삭제 후 재등록
    existing = collection.get(where={"source": filename})
    if existing["ids"]:
        collection.delete(ids=existing["ids"])
        print(f"  기존 데이터 삭제: {len(existing['ids'])}개")

    # 배치 등록 (ChromaDB 제한: 한 번에 최대 5461개)
    batch_size = 100
    for i in range(0, len(chunks), batch_size):
        end = min(i + batch_size, len(chunks))
        collection.add(
            ids=ids[i:end],
            documents=chunks[i:end],
            metadatas=metadatas[i:end],
        )
        print(f"  임베딩 저장 중: {end}/{len(chunks)}")

    print(f"  완료! {len(chunks)}개 청크가 벡터 DB에 저장되었습니다.")


# ── 질문 답변 ─────────────────────────────────────────
def ask(question: str):
    """질문에 대해 관련 PDF 내용을 검색하고 LLM으로 답변 생성"""
    collection = get_collection()

    if collection.count() == 0:
        print("[오류] 등록된 PDF가 없습니다. 먼저 PDF를 추가하세요.")
        return

    # 벡터 검색
    results = collection.query(query_texts=[question], n_results=TOP_K)

    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    # 검색 결과 출력
    print(f"\n{'='*60}")
    print(f"질문: {question}")
    print(f"{'='*60}")
    print(f"\n[검색된 관련 문서 {len(documents)}건]")
    for i, (doc, meta, dist) in enumerate(zip(documents, metadatas, distances)):
        similarity = 1 - dist  # cosine distance → similarity
        print(f"  {i+1}. [{meta['source']}] (유사도: {similarity:.2f})")
        print(f"     {doc[:100]}...")

    # 컨텍스트 구성
    context = "\n\n---\n\n".join(
        f"[출처: {m['source']}]\n{d}" for d, m in zip(documents, metadatas)
    )

    # Ollama LLM 호출
    prompt = f"""아래 참고 문서를 바탕으로 질문에 답변하세요.
참고 문서에 없는 내용은 "문서에 해당 내용이 없습니다"라고 답하세요.

## 참고 문서
{context}

## 질문
{question}

## 답변"""

    print(f"\n[답변 생성 중...]")
    resp = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={"model": CHAT_MODEL, "prompt": prompt, "stream": False},
    )
    resp.raise_for_status()
    answer = resp.json()["response"]

    print(f"\n{'─'*60}")
    print(answer.strip())
    print(f"{'─'*60}")


# ── 등록된 문서 목록 ──────────────────────────────────
def list_docs():
    """등록된 PDF 문서 목록 출력"""
    collection = get_collection()
    count = collection.count()

    if count == 0:
        print("등록된 문서가 없습니다.")
        return

    all_data = collection.get()
    sources = set()
    for meta in all_data["metadatas"]:
        sources.add(meta["source"])

    print(f"\n등록된 PDF 문서 ({len(sources)}개 파일, 총 {count}개 청크):")
    for source in sorted(sources):
        chunk_count = sum(1 for m in all_data["metadatas"] if m["source"] == source)
        print(f"  - {source} ({chunk_count}개 청크)")


# ── 대화형 모드 ──────────────────────────────────────
def interactive():
    """대화형 질의응답 모드"""
    print("\n" + "=" * 60)
    print("  PDF RAG 대화형 모드")
    print("  종료: quit / 문서목록: list")
    print("=" * 60)

    while True:
        try:
            question = input("\n질문> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n종료합니다.")
            break

        if not question:
            continue
        if question.lower() in ("quit", "exit", "종료"):
            print("종료합니다.")
            break
        if question.lower() in ("list", "목록"):
            list_docs()
            continue

        ask(question)


# ── 메인 ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="PDF RAG 시스템 (Ollama + ChromaDB)")
    subparsers = parser.add_subparsers(dest="command")

    # add: PDF 등록
    add_parser = subparsers.add_parser("add", help="PDF 파일을 벡터 DB에 등록")
    add_parser.add_argument("pdf_path", help="PDF 파일 경로")

    # ask: 질문
    ask_parser = subparsers.add_parser("ask", help="PDF 내용에 대해 질문")
    ask_parser.add_argument("question", help="질문 내용")

    # list: 등록된 문서 목록
    subparsers.add_parser("list", help="등록된 PDF 문서 목록")

    # chat: 대화형 모드
    subparsers.add_parser("chat", help="대화형 질의응답 모드")

    args = parser.parse_args()

    if args.command == "add":
        add_pdf(args.pdf_path)
    elif args.command == "ask":
        ask(args.question)
    elif args.command == "list":
        list_docs()
    elif args.command == "chat":
        interactive()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
