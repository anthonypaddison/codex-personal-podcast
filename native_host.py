#!/opt/homebrew/bin/python3
"""Chrome native messaging host; accepts only our installed extension origin."""
import fcntl
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

from workflow import Store, split_script

# Preserve the original installation, which invokes this file directly.
ORIGIN = os.environ.get('PERSONAL_PODCAST_ORIGIN', 'chrome-extension://gnppbmkakhldnkdpbibffmhdddakoccd/')
ROOT = Path.home() / 'Music' / 'Personal Podcasts'


def dispatch(store, message):
    command = message['command']
    if command == 'import':
        source = Path(message['path']).expanduser().resolve(strict=True)
        if source.suffix.lower() not in ('.txt', '.md') or not source.is_file():
            raise ValueError('Choose a .txt or .md script file.')
        if source.stat().st_size > 400000:
            raise ValueError('File too large; use smaller jobs.')
        text = source.read_bytes().decode('utf-8', errors='strict')
        split_script(text)
        return {'text': text, 'title': source.stem}
    if command == 'list':
        jobs = []
        for path in sorted(store.root.glob('*/manifest.json'), reverse=True):
            job = store.get(path.parent.name)
            jobs.append({'id': job['id'], 'title': job['title']})
        return jobs
    if command == 'create':
        return store.create(message['mode'], message.get('title', 'Podcast'), message['text'],
                            message.get('options'), message.get('limit', 2800))
    if command == 'get':
        return store.get(message['job'])
    if command == 'adopt':
        return store.adopt(message['job'], message['response'])
    if command == 'verify':
        return store.verify(message['job'], message['section'], message['response'])
    if command == 'begin':
        return store.begin(message['job'], message['section'])
    if command == 'chunk':
        return store.chunk(message['attempt'], message['sequence'], message['data'])
    if command == 'finish':
        return store.finish(message['attempt'], message.get('cancelled', False), message.get('error'))
    if command == 'approve':
        return store.approve(message['job'], message['section'])
    if command == 'finalise':
        return store.finalise(message['job'])
    if command in ('open', 'play'):
        job = store.get(message['job'])
        folder = store.folder(job['id'])
        path = folder
        if command == 'play':
            section = store.section(job, message['section'])
            if not section['audio_filename']:
                raise ValueError('No section audio to play.')
            path = folder / section['audio_filename']
        subprocess.run(['/usr/bin/open', str(path)], check=True, capture_output=True)
        return {'opened': str(path)}
    raise ValueError('Unknown command.')


def read_exact(handle, count):
    data = bytearray()
    while len(data) < count:
        part = handle.read(count - len(data))
        if not part:
            raise EOFError('Native messaging stream closed.')
        data.extend(part)
    return data


def main():
    if len(sys.argv) < 2 or sys.argv[1] != ORIGIN:
        raise SystemExit('Only the Personal Podcast extension may start this host.')
    os.umask(0o077)
    ROOT.mkdir(parents=True, exist_ok=True)
    with (ROOT / '.recorder.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('Another podcast host is active.')
        store = Store(ROOT)
        store.recover()
        while True:
            try:
                length = struct.unpack('=I', read_exact(sys.stdin.buffer, 4))[0]
                if length > 3 * 1024 * 1024:
                    raise SystemExit('Message exceeds local host limit.')
                message = json.loads(read_exact(sys.stdin.buffer, length))
            except EOFError:
                break
            try:
                result = {'id': message.get('id'), 'result': dispatch(store, message)}
            except Exception as error:
                # Only a concise failure goes back to our local extension, never document contents.
                result = {'id': message.get('id'), 'error': str(error)[:1500]}
            encoded = json.dumps(result, ensure_ascii=False).encode('utf-8')
            if len(encoded) > 1000000:
                encoded = json.dumps({'id': message.get('id'), 'error': 'Response too large; use a shorter job.'}).encode()
            sys.stdout.buffer.write(struct.pack('=I', len(encoded)) + encoded)
            sys.stdout.buffer.flush()


if __name__ == '__main__':
    main()
