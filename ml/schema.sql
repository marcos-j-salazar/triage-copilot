CREATE TABLE training_phrases (
    id SERIAL PRIMARY KEY,
    text TEXT NOT NULL,
    category TEXT NOT NULL,
    subcategory TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    source TEXT DEFAULT 'seed'
);