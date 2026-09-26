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

const pendingBadge = document.getElementById('pending-badge');
const paginationControls = document.getElementById('pagination-controls');
const pendingToolbar = document.getElementById('pending-toolbar');
const approveAllBtn = document.getElementById('approve-all-btn');
const approveAllStatus = document.getElementById('approve-all-status');

let allPendingCorrections = [];
let currentPage = 1;
const PAGE_SIZE = 8;


const SECTIONS = {
  retrain: [retrainSection, tabRetrain],
  review: [reviewSection, tabReview],
  upload: [uploadSection, tabUpload],
  documents: [ragSection, tabRag]
};

function showSection(activeSection, activeTab) {
  retrainSection.hidden = activeSection !== retrainSection;
  reviewSection.hidden = activeSection !== reviewSection;
  uploadSection.hidden = activeSection !== uploadSection;
  ragSection.hidden = activeSection !== ragSection;

  [tabRetrain, tabReview, tabUpload, tabRag].forEach(tab => {
    if (tab === activeTab) {
      tab.setAttribute('aria-current', 'page');
    } else {
      tab.removeAttribute('aria-current');
    }
  });
}

function showSectionFromHash() {
  const [section, tab] = SECTIONS[location.hash.slice(1)] || SECTIONS.retrain;
  showSection(section, tab);
  if (section === reviewSection) {
    loadPendingCorrections();
  }
}

window.addEventListener('hashchange', showSectionFromHash);

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
    retrainStatus.style.color = 'var(--error)';
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
  updatePendingBadge();
  renderPendingPage();
}

function updatePendingBadge() {
  pendingBadge.textContent = allPendingCorrections.length;
  pendingBadge.hidden = allPendingCorrections.length === 0;
}

function renderPendingPage() {
  const listEl = document.getElementById('pending-list');
  listEl.innerHTML = '';
  paginationControls.innerHTML = '';
  pendingToolbar.hidden = allPendingCorrections.length === 0;

  if (allPendingCorrections.length === 0) {
    listEl.innerHTML = '<p class="empty-note">No pending corrections.</p>';
    return;
  }

  const start = (currentPage - 1) * PAGE_SIZE;
  const end = start + PAGE_SIZE;
  const pageItems = allPendingCorrections.slice(start, end);

  pageItems.forEach(c => {
    const item = document.createElement('div');
    item.className = 'pend';
    item.innerHTML = `
      <div class="pend-text"><b></b><div></div></div>
      <div class="pend-actions">
        <button type="button" class="btn btn-good approve-btn" data-id="${c.id}">Approve</button>
        <button type="button" class="btn btn-bad reject-btn" data-id="${c.id}">Reject</button>
      </div>
    `;

    item.querySelector('.pend-text b').textContent = c.category;
    item.querySelector('.pend-text div').textContent = c.text;
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
  const totalPages = Math.ceil(allPendingCorrections.length / PAGE_SIZE);

  if (totalPages <= 1) return;

  for (let i = 1; i <= totalPages; i++) {
    const pageBtn = document.createElement('button');
    pageBtn.type = 'button';
    pageBtn.textContent = i;
    if (i === currentPage) pageBtn.setAttribute('aria-current', 'true');
    pageBtn.addEventListener('click', () => {
      currentPage = i;
      renderPendingPage();
    });
    paginationControls.appendChild(pageBtn);
  }
}

approveAllBtn.addEventListener('click', async () => {

  approveAllBtn.disabled = true;
  approveAllBtn.textContent = 'Approving...';
  approveAllStatus.textContent = '';

  try {
    const response = await fetch('/admin/approve-all-pending', {
      method: 'POST',
      headers: { 'x-api-key': STAFF_API_KEY }
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    await loadPendingCorrections();
    // Toolbar is hidden once the list is empty, so report the result in the empty state
    if (allPendingCorrections.length === 0) {
      document.getElementById('pending-list').innerHTML =
        `<p class="empty-note">Approved ${data.count} corrections. No pending corrections.</p>`;
    }
  } catch (err) {
    approveAllStatus.textContent = 'Something went wrong. Please try again.';
    console.log('Error:', err);
  } finally {
    approveAllBtn.disabled = false;
    approveAllBtn.textContent = 'Approve all';
  }
});

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
    loadPendingCorrections();
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

showSectionFromHash();

if (reviewSection.hidden) {
  loadPendingCorrections();
}
