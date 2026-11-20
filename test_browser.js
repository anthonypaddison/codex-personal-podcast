const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

test('Inspecting ChatGPT without text uses serializable scripting arguments', async () => {
  const context = vm.createContext({
    URL, importScripts() {}, chatUI() {},
    chrome: {
      storage: {session: {get: async () => ({chatTab: 1})}},
      tabs: {get: async () => ({url: 'https://chatgpt.com/c/test'}), onRemoved: {addListener() {}}, onUpdated: {addListener() {}}},
      scripting: {executeScript: async injection => {
        if (injection.args.some(value => value === undefined)) throw new Error('Value is unserializable');
        return [{result: {text: 'A visible response.'}}];
      }},
      action: {onClicked: {addListener() {}}}, runtime: {onMessage: {addListener() {}}}
    }
  });
  vm.runInContext(fs.readFileSync('capture-poc/worker.js', 'utf8'), context);
  const result = await vm.runInContext("chat('inspect')", context);
  assert.equal(result.text, 'A visible response.');
});

test('Recording status exposes playback state without marking the section complete', async () => {
  const context = vm.createContext({
    URL, importScripts() {}, chatUI() {},
    chrome: {
      storage: {session: {get: async () => ({chatTab: 1, recording: {section: 2}})}},
      tabs: {get: async () => ({url: 'https://chatgpt.com/c/test'}), onRemoved: {addListener() {}}, onUpdated: {addListener() {}}},
      scripting: {executeScript: async () => [{result: {playing: false, hasReadAloud: true}}]},
      action: {onClicked: {addListener() {}}}, runtime: {onMessage: {addListener() {}}}
    }
  });
  vm.runInContext(fs.readFileSync('capture-poc/worker.js', 'utf8'), context);
  const status = await vm.runInContext("handle({type:'status'})", context);
  assert.equal(status.playback?.playing, false);
  assert.equal(status.recording.section, 2);
});

test('A recorder failure keeps capture silent until the explicit stop path releases it', async () => {
  let trackStopped = false, listener;
  const track = {stop() { trackStopped = true; }, addEventListener() {}};
  const stream = {getTracks: () => [track], getAudioTracks: () => [track]};
  class Recorder {
    static isTypeSupported() { return true; }
    constructor() { this.state = 'inactive'; }
    start() { this.state = 'recording'; }
    stop() { this.state = 'inactive'; queueMicrotask(() => this.onstop()); }
  }
  const context = vm.createContext({
    navigator: {mediaDevices: {getUserMedia: async () => stream}}, MediaRecorder: Recorder,
    chrome: {runtime: {id: 'test', sendMessage: async () => ({}), onMessage: {addListener(fn) { listener = fn; }}}}
  });
  vm.runInContext(fs.readFileSync('capture-poc/recorder.js', 'utf8'), context);
  await vm.runInContext("start('tab-stream-id','attempt')", context);
  vm.runInContext("recorder.onerror({error:{message:'Encoder failed'}}); recorder.stop()", context);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(trackStopped, false, 'A failed encoder must not release suppression while narration may still be playing');
  await new Promise(resolve => listener({target: 'recorder', type: 'stop'}, {id: 'test'}, resolve));
  assert.equal(trackStopped, true, 'The explicit stop path must release the stream');
});

function workerHarness(recording, {sendMessage, host} = {}) {
  const state = {chatTab: 1, recording};
  const events = {};
  const calls = [];
  const tab = {url: 'https://chatgpt.com/c/test'};
  const data = keys => Object.fromEntries([keys].flat().map(key => [key, state[key]]));
  const context = vm.createContext({
    URL, importScripts() {}, chatUI() {},
    host: async (type, values) => {
      calls.push([type, values]);
      return host ? host(type, values) : {};
    },
    chrome: {
      storage: {session: {
        get: async keys => data(keys),
        set: async values => Object.assign(state, values),
        remove: async key => { delete state[key]; }
      }},
      tabs: {
        get: async () => tab, query: async () => [{id: 10}], update: async () => {},
        onUpdated: {addListener(fn) { events.updated = fn; }},
        onRemoved: {addListener(fn) { events.removed = fn; }}
      },
      action: {
        onClicked: {addListener(fn) { events.clicked = fn; }},
        setBadgeText: async () => {}, setBadgeBackgroundColor: async () => {}
      },
      tabCapture: {getMediaStreamId: async () => 'stream'},
      offscreen: {hasDocument: async () => true, closeDocument: async () => calls.push(['closeDocument'])},
      scripting: {executeScript: async () => [{result: {hasReadAloud: true, text: 'A test.'}}]},
      power: {requestKeepAwake() { calls.push(['keepAwake']); }, releaseKeepAwake() { calls.push(['release']); }},
      runtime: {
        onMessage: {addListener() {}}, getURL: path => 'chrome-extension://example/' + path,
        sendMessage: async message => {
          calls.push([message.type, message]);
          return sendMessage ? sendMessage(message) : {};
        }
      }
    }
  });
  vm.runInContext(fs.readFileSync('capture-poc/worker.js', 'utf8'), context);
  return {state, events, calls, context, tab};
}

test('Navigation stops the pinned capture exactly once and cancels its attempt', async () => {
  const {state, events, calls} = workerHarness({tabId: 1, attempt: 'existing'});
  await events.clicked({id: 2, url: 'https://chatgpt.com/'});
  assert.equal(state.chatTab, 1);
  await events.updated(2, {status: 'loading'});
  await events.updated(1, {url: 'https://chatgpt.com/c/another'});
  assert.deepEqual(calls, []);
  await Promise.all([
    events.updated(1, {status: 'loading'}),
    events.updated(1, {url: 'https://example.com/'}),
    events.removed(1)
  ]);
  assert.deepEqual(calls.map(([type]) => type), ['stop', 'finish', 'release']);
  assert.equal(calls[0][1].discard, true);
  assert.equal(calls[1][1].cancelled, true);
  assert.equal(calls[1][1].attempt, 'existing');
  assert.equal(state.recording, undefined);
  assert.match(state.failure, /navigated/);
});

test('Navigation during asynchronous start stops the eventual stream', async () => {
  let resolveStart, startEntered;
  const entered = new Promise(resolve => { startEntered = resolve; });
  const {state, events, calls, context} = workerHarness(undefined, {
    host: async type => type === 'verify' ? {matched: true} : {attempt: 'pending'},
    sendMessage: async message => {
      if (message.type !== 'start') return {};
      return new Promise(resolve => { resolveStart = resolve; startEntered(); });
    }
  });
  const result = vm.runInContext("handle({type:'arm', job:'test', section:1})", context);
  await entered;
  await events.updated(1, {status: 'loading'});
  resolveStart({active: true});
  await assert.rejects(result, /navigated/);
  assert.deepEqual(calls.map(([type]) => type), ['verify', 'begin', 'start', 'stop', 'finish', 'release']);
  assert.equal(calls[3][1].discard, true);
  assert.equal(calls[4][1].cancelled, true);
  assert.equal(state.recording, undefined);
});

test('Navigation releases capture even when the recorder message fails', async () => {
  const {state, events, calls} = workerHarness({tabId: 1, attempt: 'existing'}, {
    sendMessage: async () => { throw new Error('Recorder disconnected'); }
  });
  await events.updated(1, {url: 'https://example.com/'});
  assert.deepEqual(calls.map(([type]) => type), ['stop', 'closeDocument', 'finish', 'release']);
  assert.equal(state.recording, undefined);
});

test('An ordinary finish saves the take after stopping Read aloud', async () => {
  const {state, calls, context} = workerHarness({tabId: 1, attempt: 'existing'});
  await vm.runInContext("handle({type:'finish'})", context);
  assert.deepEqual(calls.map(([type]) => type), ['stop', 'finish', 'release']);
  assert.equal(calls[0][1].discard, false);
  assert.equal(calls[1][1].cancelled, false);
  assert.equal(state.recording, undefined);
});

test('A navigation stop releases tracks immediately and discards the recorder tail', async () => {
  let trackStopped = false, listener, recorder;
  const track = {stop() { trackStopped = true; }, addEventListener() {}};
  const stream = {getTracks: () => [track], getAudioTracks: () => [track]};
  class Recorder {
    static isTypeSupported() { return true; }
    constructor() { recorder = this; }
    start() { this.state = 'recording'; }
    stop() { this.state = 'inactive'; }
  }
  const sent = [];
  const context = vm.createContext({
    navigator: {mediaDevices: {getUserMedia: async () => stream}}, MediaRecorder: Recorder,
    chrome: {runtime: {
      id: 'test', sendMessage: async message => { sent.push(message); return {}; },
      onMessage: {addListener(fn) { listener = fn; }}
    }}
  });
  vm.runInContext(fs.readFileSync('capture-poc/recorder.js', 'utf8'), context);
  await vm.runInContext("start('tab-stream-id','attempt')", context);
  const stopped = new Promise(resolve => listener({target: 'recorder', type: 'stop', discard: true}, {id: 'test'}, resolve));
  assert.equal(trackStopped, true);
  recorder.ondataavailable({data: {size: 1}});
  await recorder.onstop();
  await stopped;
  assert.deepEqual(sent, []);
});
