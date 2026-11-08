"""Run this on CCR. Ingests a curated list of real patient-education
documents (Parkinson's Foundation + APDA -- the same two organizations
already sourcing the live corpus, extended to many more of their real
pages/booklets), chunks them, and embeds every chunk with a real
sentence-embedding model. This is the genuinely CCR-appropriate half of
expanding the RAG: batch embedding generation across dozens of real
documents benefits from a GPU in a way a 13-unit corpus never did.

This produces a KNOWLEDGE BASE of embedded passages, not new question
units -- turning a raw passage into a patient-facing question still
needs human review (same standard as every unit already in
question_corpus.json), so that step stays manual/semi-automated and
happens after this, not inside this script.

Usage:
    python ccr_build_knowledge_index.py --out out/
Requires: pip install sentence-transformers pypdf beautifulsoup4 requests
"""
import argparse
import json
import re
from pathlib import Path

import numpy as np
import requests

# Real URLs, already verified reachable/real this session (same domains
# already sourcing the live corpus) or extensions of the same fact-sheet
# library found by browsing https://www.parkinson.org/library/fact-sheets
# and https://www.apdaparkinson.org/. Add more real, verified URLs here
# rather than a broad unverified crawl.
SOURCES = [
    ("https://www.parkinson.org/library/fact-sheets/speech-swallowing", "html"),
    ("https://www.parkinson.org/library/fact-sheets/fatigue", "html"),
    ("https://www.parkinson.org/library/fact-sheets/anxiety", "html"),
    ("https://www.parkinson.org/library/fact-sheets/sleep", "html"),
    ("https://www.parkinson.org/library/fact-sheets/fall-prevention", "html"),
    ("https://www.parkinson.org/library/fact-sheets/exercise", "html"),
    ("https://www.parkinson.org/library/fact-sheets/about-parkinsons", "html"),
    ("https://www.parkinson.org/library/fact-sheets/hospital-safety", "html"),
    ("https://www.apdaparkinson.org/wp-content/uploads/2020/07/APDA-Communication-and-PD.pdf", "pdf"),
    ("https://www.parkinson.org/sites/default/files/documents/Managing-off-time-2024.pdf", "pdf"),
]

MODEL_NAME = "BAAI/bge-base-en-v1.5"  # real GPU benefit vs. a laptop-friendly small model
CHUNK_WORDS = 80
CHUNK_OVERLAP_WORDS = 15


def fetch_html_text(url: str) -> str:
    # bs4 instead of trafilatura's HTML path -- trafilatura's optional
    # lxml[html_clean] extra doesn't resolve on all lxml versions (hit
    # this for real on CCR), and bs4 has no such fragile dependency chain.
    from bs4 import BeautifulSoup

    response = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)


def fetch_pdf_text(url: str) -> str:
    from pypdf import PdfReader
    from io import BytesIO

    content = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"}).content
    reader = PdfReader(BytesIO(content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def chunk_text(text: str, source_url: str) -> list[dict]:
    words = re.sub(r"\s+", " ", text).strip().split(" ")
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + CHUNK_WORDS, len(words))
        chunk = " ".join(words[start:end]).strip()
        if len(chunk) > 40:  # skip near-empty fragments
            chunks.append({"source_url": source_url, "text": chunk})
        if end == len(words):
            break
        start = end - CHUNK_OVERLAP_WORDS
    return chunks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=Path("out"), type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    all_chunks = []
    for url, kind in SOURCES:
        print(f"fetching {url} ...")
        try:
            text = fetch_html_text(url) if kind == "html" else fetch_pdf_text(url)
        except Exception as exc:
            print(f"  skipped ({exc})")
            continue
        chunks = chunk_text(text, url)
        print(f"  {len(chunks)} chunks")
        all_chunks.extend(chunks)

    print(f"\ntotal chunks: {len(all_chunks)}")
    print("loading embedding model (first run downloads it)...")
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(MODEL_NAME)
    texts = [c["text"] for c in all_chunks]
    embeddings = model.encode(texts, show_progress_bar=True, batch_size=64)

    for chunk, vector in zip(all_chunks, embeddings):
        chunk["embedding"] = vector.tolist()

    (args.out / "knowledge_chunks.json").write_text(json.dumps(all_chunks, indent=2))
    np.save(args.out / "knowledge_embeddings.npy", np.array(embeddings))
    print(f"\nWrote {len(all_chunks)} embedded chunks to {args.out}/knowledge_chunks.json "
          f"(+ knowledge_embeddings.npy). Bring both back.")
    print("Next step (manual, not automated): review the highest-relevance "
          "chunks and draft new question_corpus.json units from them, same "
          "process as the existing 13 units -- this script builds the "
          "retrieval base, it doesn't write patient-facing question text.")


if __name__ == "__main__":
    main()
