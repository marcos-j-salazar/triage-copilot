const chatLog = document.getElementById('chat-log');
const askForm = document.getElementById('ask-form');
const askInput = document.getElementById('ask-question-input');
const askBtn = document.getElementById('ask-btn');

function clearEmptyState() {
  const empty = chatLog.querySelector('.chat-empty');
  if (empty) empty.remove();
}

function addQuestionBubble(question) {
  clearEmptyState();
  const bubble = document.createElement('div');
  bubble.className = 'chat-message chat-question';
  bubble.textContent = question;
  chatLog.appendChild(bubble);
  chatLog.scrollTop = chatLog.scrollHeight;
}

function addLoadingBubble() {
  const loading = document.createElement('div');
  loading.className = 'chat-loading';
  loading.id = 'chat-loading-indicator';
  loading.textContent = 'Thinking…';
  chatLog.appendChild(loading);
  chatLog.scrollTop = chatLog.scrollHeight;
}

function removeLoadingBubble() {
  const loading = document.getElementById('chat-loading-indicator');
  if (loading) loading.remove();
}

function addAnswerBubble(answer, sources) {
  const bubble = document.createElement('div');
  bubble.className = 'chat-message chat-answer';
  bubble.textContent = answer;
  chatLog.appendChild(bubble);

  if (sources && sources.length > 0) {
    const sourcesEl = document.createElement('div');
    sourcesEl.className = 'chat-sources';
    const preview = sources[0].slice(0, 80).replace(/\n/g, ' ');
    sourcesEl.textContent = `Source: ${preview}…`;
    chatLog.appendChild(sourcesEl);
  }

  chatLog.scrollTop = chatLog.scrollHeight;
}

function addErrorBubble(message) {
  const bubble = document.createElement('div');
  bubble.className = 'chat-message chat-answer';
  bubble.style.color = 'var(--error)';
  bubble.textContent = message;
  chatLog.appendChild(bubble);
  chatLog.scrollTop = chatLog.scrollHeight;
}

askForm.addEventListener('submit', async (e) => {
  e.preventDefault();

  const question = askInput.value.trim();
  if (!question) return;

  addQuestionBubble(question);
  askInput.value = '';
  askInput.disabled = true;
  askBtn.disabled = true;
  addLoadingBubble();

  try {
    const response = await fetch('/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question })
    });

    removeLoadingBubble();

    if (!response.ok) {
      throw new Error('Request failed');
    }

    const data = await response.json();
    addAnswerBubble(data.answer, data.sources);

  } catch (err) {
    removeLoadingBubble();
    addErrorBubble('Something went wrong. Please try again.');
    console.log('Error:', err);
  } finally {
    askInput.disabled = false;
    askBtn.disabled = false;
    askInput.focus();
  }
});