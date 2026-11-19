"""Check first-time setup without touching the real Chrome profile."""
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest


class InstallTests(unittest.TestCase):
    def test_preview_install_and_native_round_trip(self):
        with tempfile.TemporaryDirectory(prefix='podcast test ') as home:
            env = dict(os.environ, HOME=home)
            extension_id = 'a' * 32
            origin = f'chrome-extension://{extension_id}/'
            installer = Path(__file__).with_name('install.py')
            command = [sys.executable, str(installer), '--extension-id', extension_id]
            preview = json.loads(subprocess.check_output(command, env=env))
            destination = Path(preview['destination'])
            self.assertFalse(destination.parent.exists())
            subprocess.run(command + ['--install-approved'], env=env, check=True, capture_output=True)
            manifest = json.loads(destination.read_text())
            self.assertEqual(manifest, preview['registration'])
            self.assertEqual(manifest['allowed_origins'], [origin])

            request = json.dumps({'id': 1, 'command': 'list'}).encode()
            packet = struct.pack('=I', len(request)) + request
            reply = subprocess.check_output([manifest['path'], origin], input=packet, env=env)
            self.assertEqual(struct.unpack('=I', reply[:4])[0], len(reply[4:]))
            self.assertEqual(json.loads(reply[4:]), {'id': 1, 'result': []})
            rejected = subprocess.run([manifest['path'], f"chrome-extension://{'b' * 32}/"],
                                      input=packet, env=env, capture_output=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertEqual(rejected.stdout, b'')

            different = [sys.executable, str(installer), '--extension-id', 'b' * 32, '--install-approved']
            rejected = subprocess.run(different, env=env, capture_output=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertEqual(json.loads(destination.read_text()), manifest)
