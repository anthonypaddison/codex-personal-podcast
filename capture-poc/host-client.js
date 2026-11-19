let nativePort;
let nativeSerial = 0;
const nativePending = new Map();

function host(command, values = {}) {
  if (!nativePort) {
    nativePort = chrome.runtime.connectNative('local.personalpodcast');
    nativePort.onMessage.addListener(message => {
      const pending = nativePending.get(message.id);
      if (!pending) return;
      nativePending.delete(message.id);
      clearTimeout(pending.timer);
      message.error ? pending.reject(new Error(message.error)) : pending.resolve(message.result);
    });
    nativePort.onDisconnect.addListener(() => {
      const error = chrome.runtime.lastError?.message || 'Local helper disconnected; saved sections remain on disk.';
      nativePort = null;
      for (const pending of nativePending.values()) {
        clearTimeout(pending.timer);
        pending.reject(new Error(error));
      }
      nativePending.clear();
    });
  }
  const id = ++nativeSerial;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      nativePending.delete(id);
      reject(new Error('Local helper timed out. Preserve this job and reconnect.'));
    }, 660000);
    nativePending.set(id, {resolve, reject, timer});
    nativePort.postMessage({id, command, ...values});
  });
}
