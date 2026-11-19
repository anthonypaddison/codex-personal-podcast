"""Durable local jobs. No network, microphone, credentials or speech engine."""
import base64
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid


def split_script(text, limit=2800):
    if not isinstance(text, str) or not text.strip() or len(text) > 100000:
        raise ValueError('Provide between 1 and 100,000 characters of narration.')
    if not isinstance(limit, int) or not 20 <= limit <= 12000:
        raise ValueError('Section size must be between 20 and 12,000 characters.')
    # Attach paragraph separators to their original paragraph, preserving every byte.
    paragraphs = re.findall(r'.*?(?:\r?\n[ \t]*\r?\n|\Z)', text, re.S)
    sections, current = [], ''
    for paragraph in filter(None, paragraphs):
        if current and len(current) + len(paragraph) > limit:
            sections.append(current)
            current = ''
        current += paragraph
    if current:
        sections.append(current)
    return sections


def digest(data):
    return hashlib.sha256(data).hexdigest()


def wording(text):
    return re.sub(r'\s+', ' ', text).strip()


class Store:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.active = {}
        self.ffmpeg = shutil.which('ffmpeg') or '/opt/homebrew/bin/ffmpeg'
        self.ffprobe = shutil.which('ffprobe') or '/opt/homebrew/bin/ffprobe'

    def folder(self, job_id):
        if not isinstance(job_id, str) or not re.fullmatch(r'[a-z0-9-]{1,120}', job_id):
            raise ValueError('Invalid job identifier.')
        path = self.root / job_id
        if path.is_symlink() or path.resolve().parent != self.root:
            raise ValueError('Unsafe job path.')
        return path

    def get(self, job_id):
        return json.loads((self.folder(job_id) / 'manifest.json').read_text())

    def save(self, job):
        folder = self.folder(job['id'])
        temporary = folder / f'.manifest-{uuid.uuid4().hex}.tmp'
        with temporary.open('x', encoding='utf-8') as handle:
            json.dump(job, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, folder / 'manifest.json')

    def log(self, job, event):
        with (self.folder(job['id']) / 'log.txt').open('a', encoding='utf-8') as handle:
            handle.write(f'{dt.datetime.now().isoformat(timespec="seconds")} {event}\n')

    def create(self, mode, title, text, options=None, limit=2800):
        if mode not in ('script', 'generate'):
            raise ValueError('Choose script or generate mode.')
        split_script(text, limit)
        slug = re.sub(r'[^a-z0-9]+', '-', str(title).lower()).strip('-')[:45] or 'podcast'
        job_id = f'{dt.datetime.now():%Y-%m-%d-%H%M%S}-{slug}-{uuid.uuid4().hex[:8]}'
        folder = self.folder(job_id)
        folder.mkdir(mode=0o700)
        job = {'version': 1, 'id': job_id, 'title': str(title)[:120], 'mode': mode,
               'options': options or {}, 'section_limit': limit, 'sections': [],
               'final_mp3': None, 'output_folder': str(folder),
               'prompt': text if mode == 'generate' else None}
        (folder / ('original.txt' if mode == 'script' else 'prompt.txt')).write_text(text, encoding='utf-8')
        if mode == 'script':
            self._script(job, text)
        self.save(job)
        self.log(job, 'Job created; original input saved.')
        return job

    def _script(self, job, text):
        parts = split_script(text, job['section_limit'])
        job['sections'] = [
            {'number': i, 'text': part, 'sha256': digest(part.encode()),
             'status': 'pending', 'verification': None, 'attempts': [],
             'audio_filename': None, 'duration': None, 'errors': []}
            for i, part in enumerate(parts, 1)]
        (self.folder(job['id']) / 'narration.txt').write_text(text, encoding='utf-8')

    def adopt(self, job_id, response):
        job = self.get(job_id)
        if job['mode'] != 'generate' or job['sections']:
            raise ValueError('Generated script already saved; create a new job to regenerate.')
        script, separator, sources = response.partition('\n\nSOURCES\n')
        if not script.strip():
            raise ValueError('The generated script is empty.')
        if job['options'].get('research') and (not separator or not sources.strip()):
            raise ValueError('Researched narration requires a separate SOURCES block. Ask ChatGPT to supply it before saving.')
        if re.search(r'https?://|www\.', script, re.I):
            raise ValueError('Generated narration contains a spoken URL. Ask ChatGPT to put URLs only in SOURCES.')
        (self.folder(job_id) / 'generated-response.txt').write_text(response, encoding='utf-8')
        (self.folder(job_id) / 'sources.txt').write_text(sources if separator else 'No separate sources supplied.', encoding='utf-8')
        self._script(job, script.strip())
        self.save(job)
        self.log(job, 'Generated script saved before recording. Review narration.txt and sources.txt.')
        return job

    def section(self, job, number):
        if type(number) is not int or not 1 <= number <= len(job['sections']):
            raise ValueError('Invalid section number.')
        return job['sections'][number - 1]

    def verify(self, job_id, number, actual):
        job = self.get(job_id)
        section = self.section(job, number)
        expected = wording(section['text'])
        actual_words = wording(actual)
        matched = expected == actual_words
        offset = next((i for i, (a, b) in enumerate(zip(expected, actual_words)) if a != b),
                      min(len(expected), len(actual_words)))
        result = {'matched': matched, 'response_sha256': digest(actual.encode()),
                  'expected_characters': len(expected), 'actual_characters': len(actual_words),
                  'first_difference': None if matched else offset}
        section['verification'] = result
        (self.folder(job_id) / f'response-{number:04d}.txt').write_text(actual, encoding='utf-8')
        self.save(job)
        return result

    def begin(self, job_id, number):
        if self.active:
            raise ValueError('Another section is already recording.')
        if shutil.disk_usage(self.root).free < 512 * 1024 * 1024:
            raise ValueError('Less than 512 MB free: recording not started.')
        job = self.get(job_id)
        section = self.section(job, number)
        if not (section.get('verification') or {}).get('matched'):
            raise ValueError('Verify an exact ChatGPT response before recording.')
        attempt_id = uuid.uuid4().hex
        raw_name = f'section-{number:04d}-{attempt_id}.webm'
        path = self.folder(job_id) / raw_name
        path.touch(mode=0o600, exist_ok=False)
        attempt = {'attempt': attempt_id, 'raw_filename': raw_name, 'chunks': 0,
                   'status': 'recording', 'started': dt.datetime.now().isoformat()}
        section['attempts'].append(attempt)
        section['status'] = 'recording'
        job['final_mp3'] = None
        self.active[attempt_id] = (job_id, number)
        self.save(job)
        self.log(job, f'Section {number}: recording attempt {attempt_id}.')
        return {**attempt, 'raw_path': str(path)}

    def chunk(self, attempt_id, sequence, encoded):
        if attempt_id not in self.active:
            raise ValueError('Unknown or interrupted recording attempt.')
        job_id, number = self.active[attempt_id]
        job = self.get(job_id)
        attempt = self.section(job, number)['attempts'][-1]
        if type(sequence) is not int or sequence != attempt['chunks']:
            raise ValueError('Audio chunk missing, repeated or out of order; retry section.')
        if not isinstance(encoded, str) or len(encoded) > 2 * 1024 * 1024:
            raise ValueError('Invalid audio chunk size.')
        data = base64.b64decode(encoded, validate=True)
        if shutil.disk_usage(self.root).free < 256 * 1024 * 1024:
            raise ValueError('Disk space low: stop and preserve this partial section.')
        with (self.folder(job_id) / attempt['raw_filename']).open('ab') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        attempt['chunks'] += 1
        self.save(job)
        return {'chunks': attempt['chunks']}

    def run(self, arguments, folder):
        result = subprocess.run(arguments, cwd=folder, capture_output=True, text=True, timeout=600)
        if result.returncode:
            raise ValueError('Audio processing failed: ' + result.stderr[-1000:])
        return result

    def inspect_audio(self, path):
        info = json.loads(self.run([self.ffprobe, '-v', 'error', '-show_entries',
                                   'format=duration', '-of', 'json', str(path)], path.parent).stdout)
        duration = float(info['format'].get('duration', 0))
        check = self.run([self.ffmpeg, '-nostdin', '-hide_banner', '-i', str(path),
                          '-af', 'volumedetect', '-f', 'null', '-'], path.parent)
        match = re.search(r'max_volume: ([-\w.]+) dB', check.stderr)
        maximum = float(match.group(1)) if match else -math.inf
        if duration < 0.2 or not math.isfinite(duration) or maximum < -55:
            raise ValueError('Audio is too short or silent; recording requires retry.')
        return {'duration': duration, 'max_volume_db': maximum,
                'sha256': digest(path.read_bytes())}

    def finish(self, attempt_id, cancelled=False, error=None):
        if attempt_id not in self.active:
            raise ValueError('Recording no longer active.')
        job_id, number = self.active.pop(attempt_id)
        job = self.get(job_id)
        section = self.section(job, number)
        attempt = section['attempts'][-1]
        folder = self.folder(job_id)
        attempt['status'] = section['status'] = 'cancelled' if cancelled else 'review'
        if error:
            section['errors'].append(str(error)[:1000])
        if not cancelled:
            try:
                audio_name = attempt['raw_filename'].replace('.webm', '.mp3')
                self.run([self.ffmpeg, '-nostdin', '-hide_banner', '-n', '-i', attempt['raw_filename'],
                          '-map', '0:a:0', '-vn', '-ac', '1', '-ar', '48000', '-c:a', 'libmp3lame',
                          '-q:a', '2', audio_name], folder)
                technical = self.inspect_audio(folder / audio_name)
                attempt.update(technical)
                attempt['audio_filename'] = audio_name
                section.update({'audio_filename': audio_name, 'duration': technical['duration'],
                                'audio_sha256': technical['sha256']})
            except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
                attempt['status'] = section['status'] = 'error'
                section['errors'].append(str(exc))
        self.save(job)
        self.log(job, f'Section {number}: {section["status"]}; raw recording retained.')
        return job

    def approve(self, job_id, number):
        job = self.get(job_id)
        section = self.section(job, number)
        if section['status'] != 'review':
            raise ValueError('Save a successful recording before approving it.')
        self.inspect_audio(self.folder(job_id) / section['audio_filename'])
        section['status'] = 'complete'
        section['attempts'][-1]['status'] = 'complete'
        section['review'] = 'User confirmed speech, beginning and end.'
        self.save(job)
        return job

    def recover(self):
        for path in self.root.glob('*/manifest.json'):
            if path.parent.is_symlink():
                continue
            job = self.get(path.parent.name)
            changed = False
            for section in job['sections']:
                if section['status'] == 'recording':
                    section['status'] = 'interrupted'
                    section['attempts'][-1]['status'] = 'interrupted'
                    section['errors'].append('Recorder disconnected; raw chunks retained. Retry this section.')
                    changed = True
            if changed:
                self.save(job)
                self.log(job, 'Interrupted recorder recovered; completed sections preserved.')

    def finalise(self, job_id):
        job = self.get(job_id)
        if not job['sections'] or any(s['status'] != 'complete' for s in job['sections']):
            raise ValueError('Record and review every numbered section before joining.')
        folder = self.folder(job_id)
        for section in job['sections']:
            if digest((folder / section['audio_filename']).read_bytes()) != section['audio_sha256']:
                raise ValueError('Section audio changed since verification; review required.')
        # All filenames are generated locally, never supplied by the document or browser.
        listing = folder / 'join.txt'
        listing.write_text(''.join(f"file '{s['audio_filename']}'\n" for s in job['sections']))
        name = f'podcast-{uuid.uuid4().hex[:8]}.mp3'
        self.run([self.ffmpeg, '-nostdin', '-hide_banner', '-n', '-f', 'concat', '-safe', '1',
                  '-i', listing.name, '-c:a', 'libmp3lame', '-q:a', '2', name], folder)
        technical = self.inspect_audio(folder / name)
        expected = sum(section['duration'] for section in job['sections'])
        if abs(technical['duration'] - expected) > max(1, len(job['sections']) * 0.1):
            raise ValueError('Joined duration does not match section durations; raw files retained.')
        job['final_mp3'] = name
        job['final_verification'] = technical
        self.save(job)
        self.log(job, f'Joined {len(job["sections"])} reviewed sections in order: {name}.')
        return job
