const retrainBtn = document.getElementById('retrain-btn');
const retrainStatus = document.getElementById('retrain-status');
const tabRetrain = document.getElementById('tab-retrain');
const tabReview = document.getElementById('tab-review');
const tabUpload = document.getElementById('tab-upload');
const tabRag = document.getElementById('tab-rag');
const retrainSection = document.getElementById('retrain-section');
const reviewSection = document.getElementById('review-section');
const uploadSection = document.getElementById('upload-section');
const ragSection = document.getElementById('rag-section');

const calendarFileInput = document.getElementById('calendar-file-input');
const uploadCalendarBtn = document.getElementById('upload-calendar-btn');
const calendarUploadResult = document.getElementById('calendar-upload-result');

const documentFileInput = document.getElementById('document-file-input');
const uploadDocumentBtn = document.getElementById('upload-document-btn');
const documentUploadResult = document.getElementById('document-upload-result');

let allPendingCorrections = [];
let currentPage = 1;
const PAGE_SIZE = 8;

function showSection(activeSection, activeTab) {
  retrainSection.hidden = activeSection !== retrainSection;
  reviewSection.hidden = activeSection !== reviewSection;
  uploadSection.hidden = activeSection !== uploadSection;
  ragSection.hidden = activeSection !== ragSection;

  [tabRetrain, tabReview, tabUpload, tabRag].forEach(tab => {
    if (tab === activeTab) {
      tab.classList.add('btn-primary');
      tab.classList.remove('btn-outline');
    } else {
      tab.classList.add('btn-outline');
      tab.classList.remove('btn-primary');
    }
  });
}

tabRetrain.addEventListener('click', () => {
  showSection(retrainSection, tabRetrain);
});

tabReview.addEventListener('click', () => {
  showSection(reviewSection, tabReview);
  loadPendingCorrections();
});

tabUpload.addEventListener('click', () => {
  showSection(uploadSection, tabUpload);
});

tabRag.addEventListener('click', () => {
  showSection(ragSection, tabRag);
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
  const listEl = document.getElementById('pending-list');
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

  listEl.appendChild(pagination);
}

document.getElementById('upload-csv-btn').addEventListener('click', async () => {
  const fileInput = document.getElementById('csv-file-input');
  const uploadResult = document.getElementById('upload-result');
  const uploadBtn = document.getElementById('upload-csv-btn');

  const file = fileInput.files[0];
  if (!file) {
    uploadResult.textContent = 'Please select a file first.';
    return;
  }

  uploadBtn.disabled = true;
  uploadBtn.textContent = 'Uploading...';
  uploadResult.textContent = '';

  const formData = new FormData();
  formData.append('file', file);

  try {
    const response = await fetch('/admin/upload-csv', {
      method: 'POST',
      headers: { 'x-api-key': STAFF_API_KEY },
      body: formData
    });
    const data = await response.json();
    uploadResult.innerHTML = `
      <p style="color: var(--confidence-high);">Inserted: ${data.inserted}</p>
      <p style="color: var(--confidence-mid);">Skipped: ${data.skipped}</p>
    `;
  } catch (err) {
    uploadResult.textContent = 'Something went wrong. Please try again.';
    console.log('Error:', err);
  } finally {
    uploadBtn.disabled = false;
    uploadBtn.textContent = 'Upload';
  }
});

uploadCalendarBtn.addEventListener('click', async () => {
  const file = calendarFileInput.files[0];
  if (!file) {
    calendarUploadResult.textContent = 'Please select a file first.';
    return;
  }

  uploadCalendarBtn.disabled = true;
  uploadCalendarBtn.textContent = 'Uploading...';
  calendarUploadResult.textContent = '';

  const formData = new FormData();
  formData.append('file', file);

  try {
    const response = await fetch('/admin/upload-calendar', {
      method: 'POST',
      headers: { 'x-api-key': STAFF_API_KEY },
      body: formData
    });
    const data = await response.json();
    calendarUploadResult.innerHTML = `
      <p style="color: var(--confidence-high);">Uploaded "${data.document}" — ${data.chunks_created} chunks created.</p>
    `;
  } catch (err) {
    calendarUploadResult.textContent = 'Something went wrong. Please try again.';
    console.log('Error:', err);
  } finally {
    uploadCalendarBtn.disabled = false;
    uploadCalendarBtn.textContent = 'Upload Calendar';
  }
});

uploadDocumentBtn.addEventListener('click', async () => {
  const file = documentFileInput.files[0];
  if (!file) {
    documentUploadResult.textContent = 'Please select a file first.';
    return;
  }

  uploadDocumentBtn.disabled = true;
  uploadDocumentBtn.textContent = 'Uploading...';
  documentUploadResult.textContent = '';

  const formData = new FormData();
  formData.append('file', file);

  try {
    const response = await fetch('/admin/upload-document', {
      method: 'POST',
      headers: { 'x-api-key': STAFF_API_KEY },
      body: formData
    });
    const data = await response.json();
    documentUploadResult.innerHTML = `
      <p style="color: var(--confidence-high);">Uploaded "${data.document}" — ${data.chunks_created} chunks created.</p>
    `;
  } catch (err) {
    documentUploadResult.textContent = 'Something went wrong. Please try again.';
    console.log('Error:', err);
  } finally {
    uploadDocumentBtn.disabled = false;
    uploadDocumentBtn.textContent = 'Upload Document';
  }
});