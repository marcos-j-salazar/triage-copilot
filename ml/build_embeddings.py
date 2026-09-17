import openai
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()
openai.api_key = os.environ["OPENAI_API_KEY"]
engine = create_engine(os.environ["DATABASE_URL"])

SECTION_HEADERS = [
    "FALL 2026",
    "FULL SEMESTER 15-WEEK COURSES (TRADITIONAL)",
    "1st 7-WEEK COURSES (ACCELERATED)",
    "13-WEEK COURSES (SEMI-ACCELERATED)",
    "1st 6-WEEK COURSES (ACCELERATED)",
    "2nd 7-WEEK COURSES (ACCELERATED)",
    "2nd 6-WEEK COURSES (ACCELERATED)",
    "COSMO 18-WEEK COURSES",
    "HOLIDAYS, WITHDRAWAL DEADLINES AND OTHER TERM DATES",
    "SPRING 2027",
    "WINTER INTERSESSION COURSES (ACCELERATED)",
    "SUMMER 2027",
    "FULL SEMESTER 12-WEEK COURSES (SEMI-ACCELERATED)",
    "1st 10-WEEK COURSES (SEMI-ACCELERATED)",
    "2nd 10-WEEK COURSES (SEMI-ACCELERATED)",
]

def is_header_line(line):
    stripped = line.strip()
    return any(stripped.startswith(h) for h in SECTION_HEADERS)

#txt calendar
def chunk_document(filepath):
    with open(filepath, "r") as f:
        lines = f.readlines()

    chunks = []
    current = []

    for line in lines:
        if is_header_line(line):
            if current:
                chunks.append("".join(current).strip())
            current = [line]
        else:
            current.append(line)

    if current:
        chunks.append("".join(current).strip())

    return [c for c in chunks if c.strip()]

#general documents
def chunk_document_general(full_text, max_chunk_size=800, overlap=100):
    paragraphs = [p.strip() for p in full_text.split("\n\n") if p.strip()]
    chunks = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) > max_chunk_size and current:
            chunks.append(current.strip())
            current = current[-overlap:] + "\n\n" + para
        else:
            current += "\n\n" + para
    if current.strip():
        chunks.append(current.strip())
    return chunks

#calender pdfs
def chunk_calendar_text(full_text):
    lines = full_text.splitlines(keepends=True)
    chunks = []
    current = []
    for line in lines:
        if is_header_line(line):
            if current:
                chunks.append("".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        chunks.append("".join(current).strip())
    return [c for c in chunks if c.strip()]

def embed_chunk(text_chunk):
    response = openai.embeddings.create(model="text-embedding-3-small", input=text_chunk)
    return response.data[0].embedding

def store_chunk(document_name, chunk_text, embedding):
    with engine.connect() as conn:
        conn.execute(
            text("INSERT INTO document_chunks (document_name, chunk_text, embedding) VALUES (:doc, :chunk, :emb)"),
            {"doc": document_name, "chunk": chunk_text, "emb": str(embedding)}
        )
        conn.commit()

if __name__ == "__main__":
    filepath = "ml/nscc_academic_calendar.txt"
    chunks = chunk_document(filepath)
    print(f"Split into {len(chunks)} chunks")
    for i, chunk in enumerate(chunks):
        embedding = embed_chunk(chunk)
        store_chunk(filepath, chunk, embedding)
        print(f"Stored chunk {i+1}/{len(chunks)}")
    print("Done")