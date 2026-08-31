import joblib

model = joblib.load("models/model.joblib")

while True:
    text = input("\nStudent says (or 'quit'): ")

    if text.lower() == "quit":
        break

    probs = model.predict_proba([text])[0]
    results = sorted(zip(model.classes_, probs), key=lambda x: x[1], reverse=True)
    
    for label, prob in results[:3]:
        print(f"  {label}: {prob * 100:.1f}%")