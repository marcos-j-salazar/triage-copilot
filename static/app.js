const form = document.getElementById('predict-form');
const textarea = document.getElementById('student-text');
const submitBtn = document.getElementById('submit-btn');
const errorBox = document.getElementById('error-box');
const resultSection = document.getElementById('result');
const categoryNameEl = document.getElementById('result-category-name');
const confidenceFill = document.getElementById('confidence-fill');
const confidenceText = document.getElementById('confidence-text');

form.addEventListener('submit', async (e) => {
  e.preventDefault();

  const text = textarea.value.trim();
  if (!text) return;

  try {
    const response = await fetch('/predict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text })
    });

    const data = await response.json();
    console.log('Prediction result:', data);

  } catch (err) {
    console.log('Error:', err);
  }
});