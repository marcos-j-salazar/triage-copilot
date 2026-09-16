import openai
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()
openai.api_key = os.environ["OPENAI_API_KEY"]
engine = create_engine(os.environ["DATABASE_URL"])

def embed_query(query_text):
    response = openai.embeddings.create(
        model="text-embedding-3-small",
        input=query_text
    )
    return response.data[0].embedding

def find_similar_chunks(query_embedding, top_k=3):
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT chunk_text, embedding <-> :query_embedding AS distance
                FROM document_chunks
                ORDER BY distance
                LIMIT :top_k
            """),
            {"query_embedding": str(query_embedding), "top_k": top_k}
        )
        rows = result.fetchall()
    return [row[0] for row in rows]

def generate_answer(question, context_chunks):
    context = "\n\n---\n\n".join(context_chunks)
    prompt = f"""You are answering a student's question using ONLY the context below.
If the answer isn't in the context, say you don't have that information.

Context:
{context}

Question: {question}

Answer:"""

    response = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

def answer_question(question):
    query_embedding = embed_query(question)
    chunks = find_similar_chunks(query_embedding)
    answer = generate_answer(question, chunks)
    return answer, chunks

if __name__ == "__main__":
    question = "When is the deadline to withdraw from a 1st 6-week course in Fall 2026?"
    answer, chunks = answer_question(question)
    print("QUESTION:", question)
    print("\nANSWER:", answer)
    print("\n--- Retrieved chunks ---")
    for c in chunks:
        print(c[:150], "\n")