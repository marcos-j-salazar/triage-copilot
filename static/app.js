const form = document.getElementById('predict-form');
const textarea = document.getElementById('student-text');
const submitBtn = document.getElementById('submit-btn');

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  console.log('Submitted text:', textarea.value);
});