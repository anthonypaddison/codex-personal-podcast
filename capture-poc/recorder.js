// Only tabCapture stream IDs are accepted; the stream is never connected to speakers.
let recorder, stream, uploadQueue, sequence, failure, stopped, resolveStopped, requestedStop;
function base64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error('Could not read an audio chunk.'));
    reader.onload = () => resolve(reader.result.split(',')[1]);
    reader.readAsDataURL(blob);
  });
}
async function start(streamId, attempt) {
  if (recorder && recorder.state !== 'inactive') throw new Error('Already recording.');
  stream = await navigator.mediaDevices.getUserMedia({audio: {mandatory: {chromeMediaSource: 'tab', chromeMediaSourceId: streamId}}, video: false});
  if (!MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
    stream.getTracks().forEach(track => track.stop()); throw new Error('Opus/WebM recording unavailable.');
  }
  sequence = 0; failure = null; requestedStop = false; uploadQueue = Promise.resolve();
  stopped = new Promise(resolve => { resolveStopped = resolve; });
  recorder = new MediaRecorder(stream, {mimeType: 'audio/webm;codecs=opus', audioBitsPerSecond: 128000});
  recorder.ondataavailable = event => {
    if (!event.data.size) return;
    const current = sequence++;
    uploadQueue = uploadQueue.then(async () => {
      const data = await base64(event.data);
      const response = await chrome.runtime.sendMessage({target: 'worker', type: 'chunk', attempt, sequence: current, data});
      if (response.error) throw new Error(response.error);
    }).catch(async error => {
      failure = failure || error.message;
      await chrome.runtime.sendMessage({target: 'worker', type: 'recorder-error', error: failure});
      // Keep capture armed so a helper failure cannot leak narration to speakers.
      throw error;
    });
    uploadQueue.catch(() => {});
  };
  recorder.onerror = event => { failure = event.error?.message || 'Media recorder failed.'; };
  recorder.onstop = async () => {
    try { await uploadQueue; } catch (error) { failure = failure || error.message; }
    if (requestedStop) stream.getTracks().forEach(track => track.stop());
    else {
      failure = failure || 'Recorder stopped unexpectedly; stop Read aloud, then cancel and retry.';
      await chrome.runtime.sendMessage({target: 'worker', type: 'recorder-error', error: failure});
      // Hold the tab stream until the worker's explicit stop path has stopped Read aloud.
    }
    resolveStopped({error: failure});
  };
  stream.getAudioTracks().forEach(track => track.addEventListener('ended', () => {
    failure = failure || 'Tab capture ended unexpectedly; retry this section.';
    if (recorder.state !== 'inactive') recorder.stop();
    chrome.runtime.sendMessage({target: 'worker', type: 'recorder-error', error: failure});
  }));
  recorder.start(1000); return {active: true};
}
chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (sender.id !== chrome.runtime.id || message.target !== 'recorder') return;
  if (message.type === 'start') {
    start(message.streamId, message.attempt).then(respond, error => respond({error: error.message})); return true;
  }
  if (message.type === 'stop') {
    requestedStop = true;
    if (recorder && recorder.state !== 'inactive') recorder.stop();
    else if (stream) stream.getTracks().forEach(track => track.stop());
    if (stopped) stopped.then(respond); else respond({error: 'No recorder was active.'}); return true;
  }
});
