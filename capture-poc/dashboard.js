const $ = id => document.getElementById(id);
let currentJob, working = false, importedSource = null;
async function request(type, values = {}) {
  const answer = await chrome.runtime.sendMessage({target: 'worker', type, ...values});
  if (!answer) throw new Error('Extension disconnected. Reload this page and resume the saved job.');
  if (answer.error) throw new Error(answer.error);
  return answer.result;
}
const local = (command, values = {}) => request('host', {command, values});
async function action(callback) {
  if (working) return;
  working = true; $('error').textContent = '';
  document.querySelectorAll('button').forEach(button => { button.disabled = true; });
  try { await callback(); } catch (error) { $('error').textContent = error.message; }
  finally {
    working = false;
    document.querySelectorAll('button').forEach(button => { button.disabled = false; });
    await updateStatus();
  }
}
async function updateStatus() {
  if (working) return;
  try {
    const state = await request('status');
    $('status').textContent = state.recording
      ? `Recording section ${state.recording.section} silently. ${state.playback?.playing ? 'Read aloud is playing.' : state.playback ? 'Read aloud is idle. Start it when ready, or finish manually if the full passage has played.' : 'Playback state unavailable; check ChatGPT before finishing.'}`
      : state.chatTab ? 'ChatGPT connected. Select a job and prepare or arm a section.'
      : 'Open ChatGPT and click Personal Podcast to connect its tab.';
    if (state.failure) $('error').textContent = state.failure + (state.recording ? ' Stop Read aloud, then cancel and retry.' : '');
  } catch (error) { $('error').textContent = error.message; }
}
async function listJobs() {
  const jobs = await local('list'); $('jobs').replaceChildren();
  for (const job of jobs) {
    const option = document.createElement('option'); option.value = job.id;
    option.textContent = `${job.title} — ${job.id}`; $('jobs').append(option);
  }
  if (currentJob) $('jobs').value = currentJob.id;
}
function button(label, callback) {
  const element = document.createElement('button'); element.textContent = label;
  element.addEventListener('click', () => action(callback)); return element;
}
function render(job) {
  currentJob = job; $('jobPanel').hidden = false;
  $('jobTitle').textContent = job.title; $('folder').textContent = job.output_folder;
  $('generation').hidden = job.mode !== 'generate' || job.sections.length > 0;
  $('final').textContent = job.final_mp3 ? `MP3 saved: ${job.final_mp3} (${job.final_verification.duration.toFixed(1)} seconds)` : '';
  $('sections').replaceChildren();
  for (const section of job.sections) {
    const article = document.createElement('article'), title = document.createElement('h3'), text = document.createElement('pre');
    title.textContent = `Section ${section.number} of ${job.sections.length} · ${section.status}${section.duration ? ` · ${section.duration.toFixed(1)} s` : ''}`;
    text.textContent = section.text; article.append(title, text);
    const args = {job: job.id, section: section.number};
    article.append(
      button('Prepare section in ChatGPT', async () => { $('error').textContent = (await request('prepare', args)).notice; }),
      button('Arm recording / retry', async () => {
        $('error').textContent = (await request('arm', args)).notice; render(await local('get', {job: job.id}));
      }),
      button('Finish section · stop and save', async () => render(await request('finish'))),
      button('Cancel this recording', async () => render(await request('cancel'))),
      button('Play saved section', () => local('play', args)),
      button('I checked the speech, beginning and end', async () => render(await local('approve', args)))
    );
    if (section.errors.length) {
      const errors = document.createElement('p'); errors.textContent = section.errors.join('\n'); article.append(errors);
    }
    $('sections').append(article);
  }
}
$('file').addEventListener('change', () => action(async () => {
  const file = $('file').files[0]; if (!file) return;
  if (!/\.(txt|md)$/i.test(file.name)) throw new Error('Choose a UTF-8 .txt or .md file.');
  if (file.size > 400000) throw new Error('File too large; use smaller jobs.');
  importedSource = new TextDecoder('utf-8', {fatal: true}).decode(await file.arrayBuffer());
  $('input').value = importedSource;
  $('title').value = file.name.replace(/\.(txt|md)$/i, '');
}));
$('importPath').addEventListener('click', () => action(async () => {
  const result = await local('import', {path: $('filePath').value});
  importedSource = result.text;
  $('input').value = result.text;
  $('title').value = result.title;
}));
$('input').addEventListener('input', () => { importedSource = null; });
$('create').addEventListener('click', () => action(async () => {
  render(await local('create', {mode: $('mode').value, title: $('title').value, text: importedSource ?? $('input').value,
    limit: Number($('limit').value), options: {minutes: $('minutes').value, tone: $('tone').value,
      detail: $('detail').value, research: $('research').checked}})); await listJobs();
}));
$('load').addEventListener('click', () => action(async () => render(await local('get', {job: $('jobs').value}))));
$('refresh').addEventListener('click', () => action(listJobs));
$('open').addEventListener('click', () => action(() => local('open', {job: currentJob.id})));
$('generate').addEventListener('click', () => action(async () => { $('error').textContent = (await request('generate', {job: currentJob.id})).notice; }));
$('adopt').addEventListener('click', () => action(async () => render(await request('adopt', {job: currentJob.id}))));
$('join').addEventListener('click', () => action(async () => render(await local('finalise', {job: currentJob.id}))));
action(listJobs); setInterval(updateStatus, 3000);
