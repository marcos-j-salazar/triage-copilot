CREATE TABLE IF NOT EXISTS retrain_log (
    id SERIAL PRIMARY KEY,
    ran_at TIMESTAMP DEFAULT NOW(),
    swapped BOOLEAN,
    previous_accuracy FLOAT,
    new_accuracy FLOAT
);