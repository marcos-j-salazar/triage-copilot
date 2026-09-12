const retrainBtn = document.getElementById('retrain-btn');
const retrainStatus = document.getElementById('retrain-status');
const tabRetrain = document.getElementById('tab-retrain');
const tabReview = document.getElementById('tab-review');
const retrainSection = document.getElementById('retrain-section');
const reviewSection = document.getElementById('review-section');


let allPendingCorrections = [];
let currentPage = 1;
const PAGE_SIZE = 10;



tabRetrain.addEventListener('click', () => {
  retrainSection.hidden = false;
  reviewSection.hidden = true;
  tabRetrain.classList.add('btn-primary');
  tabRetrain.classList.remove('btn-outline');
  tabReview.classList.add('btn-outline');
  tabReview.classList.remove('btn-primary');
});

tabReview.addEventListener('click', () => {
  retrainSection.hidden = true;
  reviewSection.hidden = false;
  tabReview.classList.add('btn-primary');
  tabReview.classList.remove('btn-outline');
  tabRetrain.classList.add('btn-outline');
  tabRetrain.classList.remove('btn-primary');
  loadPendingCorrections();
});
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

async function loadPendingCorrections() {
  const response = await fetch('/admin/pending-corrections', {
    headers: { 'x-api-key': STAFF_API_KEY }
  });
  allPendingCorrections = await response.json();
  currentPage = 1;
  renderPendingPage();
}

function renderPendingPage() {
  const listEl = document.getElementById('pending-list');
  listEl.innerHTML = '';

  if (allPendingCorrections.length === 0) {
    listEl.innerHTML = '<p class="field-label">No pending corrections.</p>';
    return;
  }

  const start = (currentPage - 1) * PAGE_SIZE;
  const end = start + PAGE_SIZE;
  const pageItems = allPendingCorrections.slice(start, end);

  pageItems.forEach(c => {
    const item = document.createElement('div');
    item.style.marginBottom = '16px';
    item.style.paddingBottom = '16px';
    item.style.borderBottom = '1px solid var(--line)';
    item.innerHTML = `
      <p><strong>${c.category}</strong>: ${c.text}</p>
      <button type="button" class="btn btn-primary approve-btn" data-id="${c.id}">Approve</button>
      <button type="button" class="btn btn-outline reject-btn" data-id="${c.id}">Reject</button>
    `;
    listEl.appendChild(item);
  });

  document.querySelectorAll('.approve-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      await fetch('/admin/approve-correction', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-api-key': STAFF_API_KEY },
        body: JSON.stringify({ id: parseInt(btn.dataset.id) })
      });
      loadPendingCorrections();
    });
  });

  document.querySelectorAll('.reject-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      await fetch('/admin/reject-correction', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-api-key': STAFF_API_KEY },
        body: JSON.stringify({ id: parseInt(btn.dataset.id) })
      });
      loadPendingCorrections();
    });
  });

  renderPagination();
}

function renderPagination() {
  const paginationEl = document.getElementById('pagination-controls');
  paginationEl.innerHTML = '';

  const totalPages = Math.ceil(allPendingCorrections.length / PAGE_SIZE);

  if (totalPages <= 1) return;

  const pagination = document.createElement('div');
  pagination.style.marginTop = '16px';
  pagination.style.display = 'flex';
  pagination.style.gap = '8px';

  for (let i = 1; i <= totalPages; i++) {
    const pageBtn = document.createElement('button');
    pageBtn.type = 'button';
    pageBtn.textContent = i;
    pageBtn.className = i === currentPage ? 'btn btn-primary' : 'btn btn-outline';
    pageBtn.addEventListener('click', () => {
      currentPage = i;
      renderPendingPage();
    });
    pagination.appendChild(pageBtn);
  }

  paginationEl.appendChild(pagination);
}