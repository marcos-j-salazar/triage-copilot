import pandas as pd
from sklearn.model_selection import train_test_split

df = pd.read_csv("ml/seed_training_data.csv")
train_df, holdout_df = train_test_split(
    df, test_size=0.2, random_state=42, stratify=df["Category"]
)

train_df.to_csv("ml/train_only_data.csv", index=False)

holdout_df = holdout_df.rename(columns={"Phrase": "text", "Category": "category"})[["text", "category"]]
holdout_df.to_csv("ml/holdout_test_set.csv", index=False)

print(f"Train: {len(train_df)}, Holdout: {len(holdout_df)}")