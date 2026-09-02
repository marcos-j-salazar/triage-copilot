import os
import pandas as pd
from sqlalchemy import create_engine
from dotenv import load_dotenv

load_dotenv()

engine = create_engine(os.environ["DATABASE_URL"])
df = pd.read_csv("ml/seed_training_data.csv")
df.columns = df.columns.str.lower()
df.to_sql("training_phrases", engine, if_exists="append", index=False)
print(f"imported {len(df)} rows")
