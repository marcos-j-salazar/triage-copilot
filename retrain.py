import os
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sqlalchemy import text
import joblib
import shutil
from datetime import datetime, timezone
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from sqlalchemy import bindparam

load_dotenv()


s3_client = boto3.client(
    's3',
    aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"]
)

S3_BUCKET = os.environ["AWS_S3_BUCKET"]
S3_MODEL_KEY = "model.joblib"


def pull_training_data(db_engine):
    holdout_df = pd.read_csv("ml/holdout_test_set.csv")
    holdout_texts = holdout_df["text"].tolist()

    with db_engine.connect() as conn:
        result = conn.execute(
            text("SELECT text, category FROM training_phrases WHERE text NOT IN :holdout AND reviewed = TRUE").bindparams(
                bindparam("holdout", expanding=True)
            ),
            {"holdout": holdout_texts}
        )
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


def upload_model_to_s3(local_path="models/model.joblib"):
    try:
        s3_client.upload_file(local_path, S3_BUCKET, S3_MODEL_KEY)
        return True
    except ClientError as e:
        print(f"Failed to upload model to S3: {e}")
        return False


def download_model_from_s3(local_path="models/model.joblib"):
    try:
        s3_client.download_file(S3_BUCKET, S3_MODEL_KEY, local_path)
        print("Loaded model from S3")
        return True
    except ClientError as e:
        print(f"Could not download model from S3 ({e}), falling back to local file")
        return False


def load_holdout_set():
    df = pd.read_csv("ml/holdout_test_set.csv")
    return df["text"], df["category"]


def run_retrain_cycle(db_engine, current_pipeline, log_engine=None):
    df = pull_training_data(db_engine)
    new_pipeline, _, _, _, _ = train_new_pipeline(df)

    X_test_fixed, y_test_fixed = load_holdout_set()
    new_test_acc = new_pipeline.score(X_test_fixed, y_test_fixed)
    current_test_acc = evaluate_current_model(current_pipeline, X_test_fixed, y_test_fixed)

    if new_test_acc < current_test_acc:
        result = {
            "swapped": False,
            "reason": "New model did not outperform current model",
            "current_accuracy": f"{current_test_acc:.3f}",
            "new_accuracy": f"{new_test_acc:.3f}",
        }
    else:
        backup_path = backup_current_model()
        save_new_model(new_pipeline)
        s3_upload_success = upload_model_to_s3()
        result = {
            "swapped": True,
            "backup_saved_to": backup_path,
            "s3_backup_success": s3_upload_success,
            "previous_accuracy": f"{current_test_acc:.3f}",
            "new_accuracy": f"{new_test_acc:.3f}"
        }

    if log_engine is not None:
        with log_engine.connect() as conn:
            conn.execute(
                text("INSERT INTO retrain_log (swapped, previous_accuracy, new_accuracy) VALUES (:swapped, :previous_accuracy, :new_accuracy)"),
                {
                    "swapped": result["swapped"],
                    "previous_accuracy": result.get("previous_accuracy", result.get("current_accuracy")),
                    "new_accuracy": result["new_accuracy"]
                }
            )
            conn.commit()

    return result, new_pipeline if result["swapped"] else current_pipeline