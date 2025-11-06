let sessionToken = localStorage.getItem('studymate_session') || null;
let currentUser = null;

const workspaceForms = ['profileForm', 'uploadForm', 'coachForm', 'testForm'];

function buildHeaders(custom = {}) {
  const headers = { Accept: 'application/json', ...custom };
  if (sessionToken) {
    headers['X-Session-Token'] = sessionToken;
  }
  return headers;
}

async function fetchJSON(url, options = {}) {
  const headers = buildHeaders(options.headers || {});
  const response = await fetch(url, { ...options, headers });
  if (response.status === 401) {
    await handleUnauthorised();
    throw new Error('Please sign in again.');
  }
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || 'Request failed');
  }
  if (response.status === 204) {
    return null;
  }
  return response.json();
}

async function handleUnauthorised() {
  applySession(null);
  updateAuthUI(null);
  setWorkspaceEnabled(false);
  switchAuthTab('login');
}

function setStatus(online) {
  const el = document.getElementById('apiStatus');
  el.textContent = online ? 'Online' : 'Offline';
  el.classList.toggle('online', online);
}

function setWorkspaceEnabled(enabled) {
  for (const id of workspaceForms) {
    const form = document.getElementById(id);
    if (!form) continue;
    for (const element of form.elements) {
      element.disabled = !enabled;
    }
  }
  document.getElementById('coachOutput').textContent = enabled
    ? 'Ask for a plan, quiz, or summary to begin.'
    : 'Sign in to start chatting with StudyMate.';
}

function applySession(token) {
  sessionToken = token;
  if (token) {
    localStorage.setItem('studymate_session', token);
  } else {
    localStorage.removeItem('studymate_session');
  }
}

function updateAuthUI(user) {
  const loginForm = document.getElementById('loginForm');
  const registerForm = document.getElementById('registerForm');
  const meta = document.getElementById('accountMeta');
  const logoutBtn = document.getElementById('logoutBtn');

  if (user) {
    currentUser = user;
    loginForm.classList.add('hidden');
    registerForm.classList.add('hidden');
    meta.classList.remove('hidden');
    logoutBtn.classList.remove('hidden');
    meta.textContent = `${user.name} · ${user.email}`;
  } else {
    currentUser = null;
    meta.classList.add('hidden');
    logoutBtn.classList.add('hidden');
    meta.textContent = '';
    loginForm.classList.remove('hidden');
  }
}

function switchAuthTab(mode) {
  const tabs = document.querySelectorAll('.auth-tab');
  tabs.forEach((tab) => {
    tab.classList.toggle('active', tab.dataset.mode === mode);
  });
  const loginForm = document.getElementById('loginForm');
  const registerForm = document.getElementById('registerForm');
  if (mode === 'login') {
    loginForm.classList.remove('hidden');
    registerForm.classList.add('hidden');
  } else {
    loginForm.classList.add('hidden');
    registerForm.classList.remove('hidden');
  }
}

async function handleLogin(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = Object.fromEntries(new FormData(form).entries());
  const result = await fetchJSON('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  applySession(result.token);
  updateAuthUI(result.user);
  setWorkspaceEnabled(true);
  await bootstrapWorkspace();
}

async function handleRegister(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = Object.fromEntries(new FormData(form).entries());
  const result = await fetchJSON('/api/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  applySession(result.token);
  updateAuthUI(result.user);
  setWorkspaceEnabled(true);
  await bootstrapWorkspace();
}

async function handleLogout() {
  if (!sessionToken) return;
  await fetchJSON('/api/auth/logout', { method: 'POST' });
  applySession(null);
  updateAuthUI(null);
  setWorkspaceEnabled(false);
  resetWorkspace();
  switchAuthTab('login');
}

function resetWorkspace() {
  document.getElementById('profileForm').reset();
  document.getElementById('documentList').innerHTML = '';
  document.getElementById('testHistory').innerHTML = '';
  document.getElementById('insightsList').innerHTML = '<li>Sign in to see personalised analytics.</li>';
  document.getElementById('coachOutput').textContent = 'Sign in to start chatting with StudyMate.';
}

async function loadProfile() {
  const form = document.getElementById('profileForm');
  const profile = await fetchJSON('/api/profile');
  if (!profile || !Object.keys(profile).length) return;
  for (const [key, value] of Object.entries(profile)) {
    const field = form.elements.namedItem(key);
    if (field) field.value = value;
  }
}

async function saveProfile(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = Object.fromEntries(new FormData(form).entries());
  await fetchJSON('/api/profile', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  await refreshInsights();
}

async function refreshDocuments() {
  const list = document.getElementById('documentList');
  list.innerHTML = '';
  const data = await fetchJSON('/api/documents');
  if (!data.documents.length) {
    list.innerHTML = '<li>No documents yet. Add lecture notes or handouts.</li>';
    return;
  }
  for (const doc of data.documents) {
    const item = document.createElement('li');
    const topics = doc.topics?.length ? `<span>Topics: ${doc.topics.join(', ')}</span>` : '';
    item.innerHTML = `<strong>${doc.filename}</strong> · ${doc.word_count} words ${topics}`;
    list.append(item);
  }
}

async function uploadDocument(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(form);
  const headers = buildHeaders();
  headers['X-Session-Token'] && delete headers['Content-Type'];
  await fetch('/api/documents', { method: 'POST', body: data, headers });
  form.reset();
  await refreshDocuments();
  await refreshInsights();
}

async function askCoach(event) {
  event.preventDefault();
  const output = document.getElementById('coachOutput');
  output.textContent = 'Gathering trusted materials and drafting guidance…';
  const form = event.currentTarget;
  const payload = Object.fromEntries(new FormData(form).entries());
  const response = await fetchJSON('/api/coach', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  output.textContent = response.response;
  setStatus(!response.offline);
  await refreshInsights();
}

async function logTest(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = Object.fromEntries(new FormData(form).entries());
  await fetchJSON('/api/tests', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  form.reset();
  await refreshTests();
  await refreshInsights();
}

async function refreshTests() {
  const list = document.getElementById('testHistory');
  list.innerHTML = '';
  const data = await fetchJSON('/api/tests');
  if (!data.tests.length) {
    list.innerHTML = '<li>Log practice papers or quizzes to tailor future guidance.</li>';
    return;
  }
  for (const entry of data.tests) {
    const item = document.createElement('li');
    item.innerHTML = `<strong>${entry.topic}</strong> · ${entry.score}<br/><span>${entry.notes ?? ''}</span>`;
    list.append(item);
  }
}

async function refreshInsights() {
  const list = document.getElementById('insightsList');
  list.innerHTML = '';
  const data = await fetchJSON('/api/insights');
  const entries = [
    `Trusted documents: <strong>${data.documents}</strong> (${data.total_words} words)`,
    data.average_score !== null
      ? `Average assessment score: <strong>${data.average_score}%</strong>`
      : 'Average assessment score: <em>n/a</em>',
    data.weak_topics.length
      ? `Needs attention: ${data.weak_topics.join(', ')}`
      : 'Needs attention: none flagged yet',
    data.frequent_topics.length
      ? `Most practised topics: ${data.frequent_topics.join(', ')}`
      : 'Most practised topics: add more assessments',
  ];
  for (const text of entries) {
    const item = document.createElement('li');
    item.innerHTML = text;
    list.append(item);
  }
}

async function bootstrapWorkspace() {
  await Promise.all([loadProfile(), refreshDocuments(), refreshTests(), refreshInsights()]);
  setStatus(true);
}

async function bootstrapAuth() {
  if (!sessionToken) {
    setWorkspaceEnabled(false);
    return;
  }
  try {
    const me = await fetchJSON('/api/auth/me');
    updateAuthUI(me);
    setWorkspaceEnabled(true);
    await bootstrapWorkspace();
  } catch (error) {
    console.warn('Session expired', error);
    await handleUnauthorised();
  }
}

window.addEventListener('DOMContentLoaded', async () => {
  document.getElementById('profileForm').addEventListener('submit', saveProfile);
  document.getElementById('uploadForm').addEventListener('submit', uploadDocument);
  document.getElementById('coachForm').addEventListener('submit', askCoach);
  document.getElementById('testForm').addEventListener('submit', logTest);
  document.getElementById('loginForm').addEventListener('submit', handleLogin);
  document.getElementById('registerForm').addEventListener('submit', handleRegister);
  document.getElementById('logoutBtn').addEventListener('click', handleLogout);
  document.querySelectorAll('.auth-tab').forEach((tab) =>
    tab.addEventListener('click', () => switchAuthTab(tab.dataset.mode))
  );

  if (!sessionToken) {
    switchAuthTab('login');
  }

  await bootstrapAuth();
});
