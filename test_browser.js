const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

test('Inspecting ChatGPT without text uses serializable scripting arguments', async () => {
  const context = vm.createContext({
    URL, importScripts() {}, chatUI() {},
    chrome: {
      storage: {session: {get: async () => ({chatTab: 1})}},
      tabs: {get: async () => ({url: 'https://chatgpt.com/c/test'}), onRemoved: {addListener() {}}},
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
      tabs: {get: async () => ({url: 'https://chatgpt.com/c/test'}), onRemoved: {addListener() {}}},
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
