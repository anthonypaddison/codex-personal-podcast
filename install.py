"""Preview or install Chrome's native helper in the dedicated browser profile."""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extension-id', required=True, help='ID shown at chrome://extensions')
    parser.add_argument('--install-approved', action='store_true', help='Write the previewed registration')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-p]{32}', args.extension_id):
        parser.error('Expected a 32-character Chrome extension ID.')
    origin = f'chrome-extension://{args.extension_id}/'
    tools = [shutil.which(name) for name in ('ffmpeg', 'ffprobe')]
    if not all(tools):
        parser.error('FFmpeg and FFprobe must both be on your terminal PATH.')

    root = Path(__file__).resolve().parent
    directory = Path.home() / 'Library/Application Support/Personal Podcast Browser/NativeMessagingHosts'
    destination = directory / 'local.personalpodcast.json'
    launcher = directory / 'personal-podcast-host'
    tool_path = os.pathsep.join(dict.fromkeys(str(Path(tool).parent) for tool in tools))
    command = shlex.join([sys.executable, str(root / 'native_host.py')])
    script = (f'#!/bin/sh\nexport PATH={shlex.quote(tool_path)}:/usr/bin:/bin\n'
              f'export PERSONAL_PODCAST_ORIGIN={shlex.quote(origin)}\n'
              f'exec {command} "$@"\n')
    manifest = {'name': 'local.personalpodcast', 'description': 'Personal Podcast local job and MP3 helper',
                'path': str(launcher), 'type': 'stdio', 'allowed_origins': [origin]}
    if not args.install_approved:
        print(json.dumps({'destination': str(destination), 'registration': manifest}, indent=2))
        return
    if destination.is_symlink() or (destination.exists() and json.loads(destination.read_text()) != manifest):
        raise SystemExit(f'A different host is registered at {destination}; refusing to overwrite it.')
    if launcher.is_symlink() or (launcher.exists() and launcher.read_text() != script):
        raise SystemExit(f'A different launcher exists at {launcher}; refusing to overwrite it.')
    os.umask(0o077)
    directory.mkdir(parents=True, exist_ok=True)
    if not launcher.exists():
        with launcher.open('x') as handle:
            handle.write(script)
        launcher.chmod(0o700)
    if not destination.exists():
        with destination.open('x') as handle:
            handle.write(json.dumps(manifest, indent=2) + '\n')
    print(f'Installed: {destination}')


if __name__ == '__main__':
    main()
