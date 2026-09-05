const form = document.getElementById('predict-form');
const textarea = document.getElementById('student-text');
const submitBtn = document.getElementById('submit-btn');
const errorBox = document.getElementById('error-box');
const resultSection = document.getElementById('result');
const categoryNameEl = document.getElementById('result-category-name');
const confidenceFill = document.getElementById('confidence-fill');
const confidenceText = document.getElementById('confidence-text');
const confirmYesBtn = document.getElementById('confirm-yes');
const confirmNoBtn = document.getElementById('confirm-no');
const correctionStep = document.getElementById('correction-step');
const verifyStep = document.getElementById('verify-step');
const correctCategorySelect = document.getElementById('correct-category');
const saveCorrectionBtn = document.getElementById('save-correction');
const confirmationMsg = document.getElementById('confirmation-msg');
const cancelCorrectionBtn = document.getElementById('cancel-correction');

let currentText = '';

function confidenceTier(score) {
  if (score >= 0.5) {
    return { color: 'var(--confidence-high)', label: 'High confidence' };
  }
  if (score >= 0.3) {
    return { color: 'var(--confidence-mid)', label: 'Worth a second look' };
  }
  return { color: 'var(--confidence-low)', label: 'Low confidence, please verify' };
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();

  const text = textarea.value.trim();
  currentText = text;
  if (!text) return;

  verifyStep.hidden = false;
  correctionStep.hidden = true;
  confirmationMsg.hidden = true;
  confirmYesBtn.disabled = false;
  confirmNoBtn.disabled = false;

  try {
    const response = await fetch('/predict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text })
    });

    const data = await response.json();
    const { category, confidence } = data;
    const tier = confidenceTier(confidence);

    categoryNameEl.textContent = category;
    confidenceFill.style.width = `${Math.round(confidence * 100)}%`;
    confidenceFill.style.backgroundColor = tier.color;
    confidenceText.textContent = `${Math.round(confidence * 100)}% - ${tier.label}`;

    resultSection.hidden = false;

  } catch (err) {
    console.log('Error:', err);
  }
});

confirmYesBtn.addEventListener('click', () => {
  verifyStep.hidden = true;
  confirmationMsg.textContent = "Confirmed!";
  confirmationMsg.hidden = false;
});

confirmNoBtn.addEventListener('click', () => {
  correctionStep.hidden = false;
  confirmYesBtn.disabled = true;
  confirmNoBtn.disabled = true;
});

cancelCorrectionBtn.addEventListener('click', () => {
  correctionStep.hidden = true;
  confirmYesBtn.disabled = false;
  confirmNoBtn.disabled = false;
});

saveCorrectionBtn.addEventListener('click', async () => {
  const correctCategory = correctCategorySelect.value;
  saveCorrectionBtn.disabled = true;
  saveCorrectionBtn.textContent = 'Saving…';

  try {
    const response = await fetch('/update-data', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': STAFF_API_KEY
      },
      body: JSON.stringify({
        text: currentText,
        correct_category: correctCategory
      })
    });

    const data = await response.json();
    console.log('Correction saved:', data);

    correctionStep.hidden = true;
     verifyStep.hidden = true;
    confirmationMsg.textContent = 'Correction Saved!';
    confirmationMsg.hidden = false;

  } catch (err) {
    console.log('Error saving correction:', err);
  } finally {
    saveCorrectionBtn.disabled = false;
    saveCorrectionBtn.textContent = 'Save correction';
  }
});
