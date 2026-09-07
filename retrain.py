import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sqlalchemy import text
import joblib
import shutil
from datetime import datetime, timezone


def pull_training_data(db_engine):
    with db_engine.connect() as conn:
        result = conn.execute(text("SELECT text, category FROM training_phrases"))
        rows = result.fetchall()
    df = pd.DataFrame(rows, columns=["text", "category"])
    return df


def train_new_pipeline(df):
    X = df["text"]
    y = df["category"]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    pipeline = Pipeline([
        ("vectorizer", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, lowercase=True)),
        ("classifier", LogisticRegression(class_weight="balanced", max_iter=1000))
    ])
    pipeline.fit(X_train, y_train)

    train_accuracy = pipeline.score(X_train, y_train)
    test_accuracy = pipeline.score(X_test, y_test)

    return pipeline, train_accuracy, test_accuracy, X_test, y_test


def evaluate_current_model(current_pipeline, X_test, y_test):
    return current_pipeline.score(X_test, y_test)


def backup_current_model(model_path="models/model.joblib"):
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = f"models/model_backup_{timestamp}.joblib"
    shutil.copy(model_path, backup_path)
    return backup_path


def save_new_model(pipeline, model_path="models/model.joblib"):
    joblib.dump(pipeline, model_path)