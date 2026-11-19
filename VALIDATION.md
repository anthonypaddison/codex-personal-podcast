# Validation evidence

Date: 2 November 2026. Mac: macOS 27.2, Apple Silicon. FFmpeg, FFprobe, Python and Chrome were already present.

## Initial capture proof

- Built-in browser opened ChatGPT, but advertised no audio-capture capability.
- A separate local Chrome profile loaded a small extension using supported `chrome.tabCapture` and an offscreen MediaRecorder.
- Visible ChatGPT response matched `capture-poc/TEST-PASSAGE.txt` exactly.
- Actual Read aloud playback was recorded with no speaker connection from the captured stream.
- A blank TextEdit window was brought forward during the test; the capture continued.
- A separate `afplay` process played the Mac Glass chime. The tester confirmed: “Chime audible; narration silent”.
- Raw capture decoded to a 47.76-second MP3 with speech between approximately 16.09 and 30.03 seconds; peak -5.7 dB. A 14.8-second listening copy retained margins around that passage.
- The tester played the listening copy and confirmed the expected voice and full passage, including beginning and end.
- Chrome's recording-related sleep assertions were present while armed and absent after stopping. Existing sleep assertions were preserved.

## Full workflow

- The tester explicitly approved native-helper activation and the added selected-tab scripting/native-messaging permissions. Registration was installed only in the dedicated profile, with the exact extension origin as its sole allowed caller.
- Created a two-section job through the installed dashboard. Attempting to arm it against the wrong ChatGPT response failed with a text mismatch, before capture started.
- Prepared both sections in ChatGPT, sent them through the visible composer, and passed exact-wording verification before recording each.
- Section one recorded with the ChatGPT tab behind the dashboard. It saved a 69-second MP3, including manual waiting time; audible content spans approximately 9.79–15.42 seconds.
- Section two was deliberately started and cancelled. Cancellation retained its raw attempt. Retrying only section two produced another recording and a 30.72-second MP3; audible content spans approximately 8.81–14.55 seconds. Section one's file hash remained unchanged.
- Created a prompt-generated fictional garden narration through the dashboard. The original prompt and final narration were saved, and the SOURCES block was saved separately. The saved narration was sent back to ChatGPT for exact Read aloud verification before capture.
- Generated narration recorded to a 35.34-second MP3. The dashboard correctly showed Read aloud playing, then idle, while capture remained armed until manual finish. This tests the final playback-status code.
- All three MP3s decoded successfully, had non-silent audio and passed exact pre-recording text checks. Raw captures and all attempts remain available.
- A 23-second combined listening copy omits only the surrounding waiting time, with half-second speech margins. The tester confirmed all three passages were complete, correct and in order, including their beginning and end. All three source sections are now marked complete.
- Joined the two-section recording through the installed dashboard into `podcast-45a07333.mp3` (99.72 seconds). Finalised the generated recording into `podcast-4960a7fb.mp3` (35.34 seconds), using the same local production code under an exclusive file lock after disconnecting the idle helper. The latter avoided an unreliable saved-job selector in the computer-control interface.
- Both final MP3s decoded successfully. Decoded durations match their manifest durations and ordered source sections. An independent comparison of 20 ms audio-energy windows against each reviewed section, including its first and last spoken portions, exceeded 0.9999 similarity for every section. This verifies retention and order through final encoding; it is not an independent speech transcript.
- The native macOS file picker showed a selected valid Markdown document but disabled Open, including with All Files selected. Added and browser-tested the local path-import fallback. It preserved the test file's original UTF-8 bytes exactly in original.txt, narration.txt and the section manifest. A regression test covers CRLF preservation and refusal of unsupported files and misleading symlinks.
- No Chrome recording-related sleep assertions remained after the tests. Pre-existing system sleep assertions were left unchanged.
- Opened `Personal Podcast.command` through Finder, then verified Chrome had opened the local dashboard and a new ChatGPT tab in the dedicated profile. The shortcut uses the installed Chrome and no additional package.
- Current extension: 0.2.2. A further regression fix keeps the silent tab stream alive if the encoder stops unexpectedly, until the explicit stop path has stopped Read aloud. No new packages, audio drivers, paid tools, TTS APIs, microphone access or system-wide audio routing were installed or used.

The tester listened to the source recordings. Their final joins passed decoding, duration and audio-pattern retention checks. Storage recovery tests simulated recorder termination. This acceptance run did not cover live researched generation or long unattended recordings. Browser UI changes can require updates to visible-DOM selectors. Waiting silence is intentionally retained.

## Automated checks

The original acceptance run passed 14 Python tests and 3 JavaScript regression tests. Coverage includes actual FFmpeg encoding/decoding of a synthetic fixture, a two-section join, cancellation/retry, preserving completed sections, crash recovery, input/path validation, UTF-8/CRLF import, unique jobs, exact wording verification, generated-script/source separation, required research sources, rejection of spoken URLs, Chrome scripting argument compatibility, playback-state reporting and holding silent capture through encoder failure until explicit stop. JavaScript syntax and Python compilation checks pass.
