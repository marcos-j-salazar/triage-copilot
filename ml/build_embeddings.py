import openai
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()
openai.api_key = os.environ["OPENAI_API_KEY"]
engine = create_engine(os.environ["DATABASE_URL"])

def chunk_document(filepath):
    with open(filepath, "r") as f:
        content = f.read()

    raw_chunks = content.split("\n\n")
    raw_chunks = [c.strip() for c in raw_chunks if c.strip()]

    merged_chunks = []
    buffer = ""
    for chunk in raw_chunks:
        if len(chunk) < 60:
            buffer += chunk + "\n\n"
        else:
            merged_chunks.append(buffer + chunk)
            buffer = ""
    if buffer:
        merged_chunks.append(buffer.strip())

    return merged_chunks
def embed_chunk(text_chunk):
    response = openai.embeddings.create(
        model="text-embedding-3-small",
        input=text_chunk
    )
    return response.data[0].embedding

def store_chunk(document_name, chunk_text, embedding):
    with engine.connect() as conn:
        conn.execute(
            text("INSERT INTO document_chunks (document_name, chunk_text, embedding) VALUES (:doc, :chunk, :emb)"),
            {"doc": document_name, "chunk": chunk_text, "emb": str(embedding)}
        )
        conn.commit()

if __name__ == "__main__":
    filepath = "nscc_academic_calendar.txt"
    chunks = chunk_document(filepath)
    print(f"Split into {len(chunks)} chunks")

    for i, chunk in enumerate(chunks):
        embedding = embed_chunk(chunk)
        store_chunk(filepath, chunk, embedding)
        print(f"Stored chunk {i+1}/{len(chunks)}")

    print("Done")