const form = document.querySelector('#setup');
const input = document.querySelector('#hub');
const error = document.querySelector('#error');
const save = document.querySelector('#save');
const cancel = document.querySelector('#cancel');
const invoke = window.__TAURI__?.core?.invoke;

function showError(message) {
  error.textContent = String(message);
  error.hidden = false;
}

async function initialize() {
  if (!invoke) {
    save.disabled = true;
    showError('Open this page in the Buzz Mac app.');
    return;
  }
  try {
    const info = await invoke('setup_info');
    input.value = info.hub_url || '';
    cancel.hidden = !info.hub_url;
    if (info.error) showError(info.error);
    input.focus();
  } catch (err) {
    showError(err);
  }
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  error.hidden = true;
  save.disabled = true;
  try {
    await invoke('save_hub', { url: input.value.trim() });
  } catch (err) {
    showError(err);
    save.disabled = false;
  }
});

cancel.addEventListener('click', async () => {
  try { await invoke('open_dashboard'); }
  catch (err) { showError(err); }
});

initialize();
