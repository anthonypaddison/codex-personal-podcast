"""Safety and recovery contracts; uses only Python's standard library."""
import base64
import json
import io
import math
import struct
import tempfile
import unittest
import wave
from pathlib import Path

import workflow
from native_host import dispatch


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = workflow.Store(Path(self.temp.name))

    def job(self, text='First paragraph.\n\nSecond paragraph.', limit=20):
        return self.store.create('script', 'A test / title', text, {}, limit)

    def test_split_never_loses_or_reorders_original_bytes(self):
        text = 'First paragraph.\n\nSecond paragraph.\n\nThird.\n'
        sections = workflow.split_script(text, 20)
        self.assertEqual(sections, ['First paragraph.\n\n', 'Second paragraph.\n\n', 'Third.\n'])
        self.assertEqual(''.join(sections), text)

    def test_long_paragraph_is_not_silently_cut(self):
        self.assertEqual(workflow.split_script('A' * 40, 20), ['A' * 40])

    def test_new_jobs_never_overwrite_and_original_is_retained(self):
        first = self.job()
        second = self.job()
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual((self.store.folder(first['id']) / 'original.txt').read_text(),
                         'First paragraph.\n\nSecond paragraph.')

    def test_verify_blocks_rewritten_repeated_and_truncated_responses(self):
        job = self.job('A red boat crosses the harbour.')
        response = self.store.folder(job['id']) / 'response-0001.txt'
        for actual in ['A blue boat crosses the harbour.', 'A red boat.',
                       'A red boat crosses the harbour. A red boat crosses the harbour.']:
            with self.subTest(actual=actual):
                result = self.store.verify(job['id'], 1, actual)
                self.assertFalse(result['matched'])
                self.assertFalse(response.exists())
                with self.assertRaises(ValueError):
                    self.store.begin(job['id'], 1)

    def test_mismatch_preserves_the_last_verified_response(self):
        job = self.job('A test.')
        folder = self.store.folder(job['id'])
        self.store.verify(job['id'], 1, 'A test.')
        self.store.verify(job['id'], 1, 'Unrelated private reply.')
        self.assertEqual((folder / 'response-0001.txt').read_text(), 'A test.')
        self.assertNotIn('Unrelated private reply.', (folder / 'manifest.json').read_text())
        self.assertFalse(self.store.get(job['id'])['sections'][0]['verification']['matched'])

    def test_only_layout_whitespace_is_ignored_in_verification(self):
        job = self.job('First paragraph.\n\nSecond paragraph.', 100)
        result = self.store.verify(job['id'], 1, 'First paragraph. Second paragraph.')
        self.assertTrue(result['matched'])
        self.assertEqual(self.store.get(job['id'])['sections'][0]['text'],
                         'First paragraph.\n\nSecond paragraph.')

    def test_out_of_order_or_duplicate_chunks_fail_without_corrupting_raw(self):
        job = self.job('A test.')
        self.store.verify(job['id'], 1, 'A test.')
        attempt = self.store.begin(job['id'], 1)
        self.store.chunk(attempt['attempt'], 0, base64.b64encode(b'first').decode())
        with self.assertRaises(ValueError):
            self.store.chunk(attempt['attempt'], 0, base64.b64encode(b'duplicate').decode())
        self.assertEqual(Path(attempt['raw_path']).read_bytes(), b'first')

    def test_crash_recovery_keeps_raw_and_requires_retry(self):
        job = self.job('A test.')
        self.store.verify(job['id'], 1, 'A test.')
        attempt = self.store.begin(job['id'], 1)
        self.store.chunk(attempt['attempt'], 0, base64.b64encode(b'partial').decode())
        recovered = workflow.Store(Path(self.temp.name))
        recovered.recover()
        section = recovered.get(job['id'])['sections'][0]
        self.assertEqual(section['status'], 'interrupted')
        self.assertEqual(Path(attempt['raw_path']).read_bytes(), b'partial')
        self.assertIsNone(section.get('audio_filename'))

    def test_unreviewed_or_missing_sections_block_final_mp3(self):
        job = self.job()
        with self.assertRaises(ValueError):
            self.store.finalise(job['id'])
        self.assertFalse((self.store.folder(job['id']) / 'podcast.mp3').exists())

    def test_generated_script_and_sources_saved_before_recording(self):
        job = self.store.create('generate', 'Prompt', 'Explain rain.', {'tone': 'calm'}, 100)
        saved = self.store.adopt(job['id'], 'Rain falls from clouds.\n\nSOURCES\nMet Office')
        self.assertEqual(saved['sections'][0]['text'], 'Rain falls from clouds.')
        folder = self.store.folder(job['id'])
        self.assertEqual((folder / 'sources.txt').read_text(), 'Met Office')
        self.assertEqual((folder / 'prompt.txt').read_text(), 'Explain rain.')

    def test_researched_generation_requires_separate_sources(self):
        job = self.store.create('generate', 'Research', 'Explain rain.', {'research': True}, 100)
        with self.assertRaises(ValueError):
            self.store.adopt(job['id'], 'Rain falls from clouds.')
        self.assertFalse(self.store.get(job['id'])['sections'])

    def test_spoken_urls_are_not_accepted_as_generated_narration(self):
        job = self.store.create('generate', 'Research', 'Explain rain.', {}, 100)
        with self.assertRaises(ValueError):
            self.store.adopt(job['id'], 'Visit https://example.com for details.\n\nSOURCES\nExample')

    def test_path_import_preserves_utf8_and_rejects_other_files(self):
        source = Path(self.temp.name) / 'script.md'
        source.write_bytes('A café.\r\n\r\nThe end.\r\n'.encode('utf-8'))
        result = dispatch(self.store, {'command': 'import', 'path': str(source)})
        self.assertEqual(result['text'], 'A café.\r\n\r\nThe end.\r\n')
        secret = Path(self.temp.name) / '.env'
        secret.write_text('not script content')
        alias = Path(self.temp.name) / 'alias.md'
        alias.symlink_to(secret)
        for path in [secret, alias]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                dispatch(self.store, {'command': 'import', 'path': str(path)})

    def test_untrusted_paths_and_empty_scripts_are_rejected(self):
        for name in ['../escape', '/tmp/outside', 'bad\\path']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.store.get(name)
        with self.assertRaises(ValueError):
            self.job('   ')

    def test_cancel_retry_and_join_preserve_successful_sections(self):
        job = self.job()
        # A real one-second WAV fixture tests encoding and decoding, not an existence check.
        audio = io.BytesIO()
        with wave.open(audio, 'wb') as wav:
            wav.setparams((1, 2, 48000, 0, 'NONE', 'not compressed'))
            wav.writeframes(b''.join(struct.pack('<h', int(6000 * math.sin(i * 2 * math.pi * 440 / 48000)))
                                     for i in range(48000)))
        for number, text in [(1, 'First paragraph.'), (2, 'Second paragraph.')]:
            self.store.verify(job['id'], number, text)
            attempt = self.store.begin(job['id'], number)
            self.store.chunk(attempt['attempt'], 0, base64.b64encode(audio.getvalue()).decode())
            self.store.finish(attempt['attempt'])
            self.store.approve(job['id'], number)
        before = self.store.get(job['id'])['sections'][0]
        attempt = self.store.begin(job['id'], 2)
        self.store.chunk(attempt['attempt'], 0, base64.b64encode(b'cancelled bytes').decode())
        self.store.finish(attempt['attempt'], cancelled=True)
        self.assertEqual(self.store.get(job['id'])['sections'][0], before)
        with self.assertRaises(ValueError):
            self.store.finalise(job['id'])
        # Retry only the failed section and retain all prior raw attempts.
        attempt = self.store.begin(job['id'], 2)
        self.store.chunk(attempt['attempt'], 0, base64.b64encode(audio.getvalue()).decode())
        self.store.finish(attempt['attempt'])
        self.store.approve(job['id'], 2)
        final = self.store.finalise(job['id'])
        self.assertAlmostEqual(final['final_verification']['duration'], 2.064, delta=0.15)
        self.assertGreater(final['final_verification']['max_volume_db'], -30)
        self.assertEqual(len(final['sections'][1]['attempts']), 3)
        self.assertEqual(self.store.get(job['id'])['sections'][0], before)


if __name__ == '__main__':
    unittest.main()
