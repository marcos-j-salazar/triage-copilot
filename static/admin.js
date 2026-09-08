const retrainBtn = document.getElementById('retrain-btn');
const retrainStatus = document.getElementById('retrain-status');

retrainBtn.addEventListener('click', async () => {
  retrainBtn.disabled = true;
  retrainBtn.textContent = 'Retraining...';
  retrainStatus.hidden = true;

  try {
    const response = await fetch('/retrain', {
      method: 'POST',
      headers: {
        'x-api-key': STAFF_API_KEY
      }
    });

    const data = await response.json();

    if (response.status === 429) {
  retrainStatus.style.color = 'var(--confidence-mid)';
  retrainStatus.textContent = data.detail;
} else if (data.swapped) {
  retrainStatus.style.color = 'var(--confidence-high)';
  retrainStatus.textContent = `Model updated. Previous accuracy: ${data.previous_accuracy}, new accuracy: ${data.new_accuracy}.`;
} else {
  retrainStatus.style.color = 'var(--ink-soft)';
  retrainStatus.textContent = `No update made. New model (${data.new_accuracy}) did not outperform current model (${data.current_accuracy}).`;
}

    retrainStatus.hidden = false;

  } catch (err) {
    retrainStatus.textContent = 'Something went wrong. Please try again.';
    retrainStatus.hidden = false;
    console.log('Error:', err);
  } finally {
    retrainBtn.disabled = false;
    retrainBtn.textContent = 'Retrain Model';
  }
});