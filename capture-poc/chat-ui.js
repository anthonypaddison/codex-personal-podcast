// Visible DOM only. No internal ChatGPT endpoints, app stores, cookies or tokens.
function chatUI(operation, text) {
  if (location.origin !== 'https://chatgpt.com') throw new Error('Select a ChatGPT tab.');
  const visible = e => e.getClientRects().length > 0;
  const buttons = [...document.querySelectorAll('button[aria-label]')].filter(visible);
  const named = label => buttons.filter(e => e.getAttribute('aria-label') === label).at(-1);
  const stop = named('Stop reading aloud');
  const roots = [...document.querySelectorAll('[data-markdown-text-style="assistant-message"], [data-message-author-role="assistant"] .markdown')].filter(visible);
  const root = roots.at(-1);
  const result = {
    text: root?.innerText || '', count: roots.length,
    playing: Boolean(stop), hasReadAloud: Boolean(named('Read aloud')),
    generating: Boolean(named('Stop generating') || named('Stop streaming')),
    url: location.href
  };
  if (operation === 'inspect') return result;
  if (operation === 'stop') {
    if (stop) stop.click();
    return result;
  }
  if (operation === 'read') {
    if (!root || !named('Read aloud') || stop || result.generating) throw new Error('Read aloud is not ready.');
    named('Read aloud').click();
    return result;
  }
  if (operation === 'prepare') {
    if (stop || result.generating) throw new Error('Wait for the current response or playback to finish.');
    const editor = [...document.querySelectorAll('[contenteditable="true"][role="textbox"],#prompt-textarea')].find(visible);
    if (!editor) throw new Error('Chat composer unavailable. Sign in or reload ChatGPT.');
    if (editor.innerText.trim()) throw new Error('Chat composer contains a draft; preserve or send it first.');
    editor.focus();
    const selection = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(editor);
    selection.removeAllRanges();
    selection.addRange(range);
    if (!document.execCommand('insertText', false, text)) throw new Error('Could not fill composer. Paste manually.');
    return result;
  }
  if (operation === 'send') {
    const send = named('Send') || named('Send prompt');
    if (!send || send.disabled) throw new Error('Send is not ready; use ChatGPT’s Send button.');
    send.click();
    return result;
  }
  throw new Error('Unknown chat operation.');
}
