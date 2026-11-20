# Personal Podcast

> **No longer maintained.** The source is available under the [MIT License](LICENSE). This workflow depends on the ChatGPT web interface and Chrome tab capture. Changes to either may stop it working.

Turn a script or a ChatGPT prompt into a local MP3 using ChatGPT **Read aloud**. The extension captures only the selected tab in a dedicated Chrome profile. Your other apps can continue playing sound.

If you received a Git bundle, clone it with `git clone "/path/to/Personal Podcast.bundle" personal-podcast`, then follow the setup below.

## Set up on a Mac

You need Google Chrome 116 or later in Applications, Python 3.9 or later, and `ffmpeg` and `ffprobe` on your terminal PATH. Node.js is needed only for the JavaScript tests. You also need access to ChatGPT with **Read aloud** available.

1. Clone this repository into a permanent folder and open Terminal in that folder.
2. Start the dedicated browser profile:

   ```sh
   open -na "/Applications/Google Chrome.app" --args \
     --user-data-dir="$HOME/Library/Application Support/Personal Podcast Browser" \
     --no-first-run --no-default-browser-check "chrome://extensions"
   ```

3. In that window, enable **Developer mode**, click **Load unpacked**, and select the checkout's `capture-poc` folder. Copy the Personal Podcast extension ID shown by Chrome.
4. In Terminal, replace `YOUR_EXTENSION_ID` with that ID. First preview the registration, then install it:

   ```sh
   python3 install.py --extension-id YOUR_EXTENSION_ID
   python3 install.py --extension-id YOUR_EXTENSION_ID --install-approved
   ```

   The helper is registered only in the dedicated browser's data directory and accepts only the specified extension. The installer preserves a different existing registration. Keep the checkout in the same location because Chrome's unpacked extension ID and the installed launcher depend on it.
5. In the dedicated Chrome window, open `https://chatgpt.com/` and sign in if prompted. Open **Extensions → Personal Podcast** while on the ChatGPT tab to connect it and open the local dashboard. Start with the bundled `capture-poc/TEST-PASSAGE.txt` before attempting a long job.

To use it again, open the same dedicated profile and click the extension on the ChatGPT tab. Existing installations can continue using their **Personal Podcast.command** shortcut.

## Existing script

1. Choose **Read an existing script exactly**. Paste text, select a UTF-8 `.txt`/`.md` file, or enter its full path and click **Import file by path**. The path option is the tested fallback if macOS disables the file picker's Open button. Save a new job.
2. For each numbered section, click **Prepare section in ChatGPT**. In ChatGPT, click **Send** and wait for the entire response.
3. Return to the dashboard and click **Arm recording / retry**. The returned text must match before arming succeeds. Only layout whitespace is normalised for this comparison; original text is preserved verbatim in the manifest and narration file.
4. In ChatGPT, click **Read aloud**. The tab is captured silently. Continue using other apps; keep the browser and Mac open.
5. The dashboard shows whether Read aloud is playing or idle. After the complete passage has played, click **Finish section · stop and save**. This stops any remaining Read aloud playback before releasing capture. Idle can also mean playback has not started, was paused, or failed; no silence timer marks completion. Closing the recording tab, leaving ChatGPT in that tab, or starting a full page load stops capture and cancels the attempt. Reopen the saved job to retry.
6. Play the saved section and check its beginning, end and wording. Click **I checked the speech, beginning and end** only after doing so.
7. Join reviewed sections into one MP3. The output folder button opens the result.

For safety, wait for playback to end before finishing. Finishing early can produce a technically valid but incomplete MP3; the review step exists to catch this. Starting Read aloud before arming can produce audible speech and miss the beginning.

## Generate from a prompt

Choose **Generate a script from a prompt**, enter a topic and optional minutes, tone, detail and research setting, and save a new job. Prepare the generation prompt, click Send in ChatGPT, and wait for completion. Click **Save ChatGPT’s generated script**. Review `narration.txt` and `sources.txt`, then record the numbered sections using the steps above. Saving a generated script never starts playback or recording. Factual accuracy still requires human review.

## Examples

- Paste a short personal essay in existing-script mode and save it as “Evening reading”.
- Select a UTF-8 `chapter.md`, use 2,800 characters per section, and record each section in order.
- Generate from “Explain why autumn leaves change colour for a curious adult”, with five minutes, a warm tone and research enabled. Review the script and separate sources before recording.

## Files and recovery

Each job lives in `~/Music/Personal Podcasts/<unique-job>/` with original input, narration, `manifest.json`, response text, raw section WebM attempts, section MP3s, final MP3 and a concise log. Generated jobs also save the full generated response and separate sources. Filenames never reuse another job or recording attempt. This folder and the dedicated browser profile are outside the checkout.

The recorder sends numbered chunks to disk once per second. Missing, duplicate or out-of-order chunks fail the section. Cancellation preserves captured chunks and all earlier recordings. After a crash, reopen the app, reconnect the ChatGPT tab and open the saved job. Interrupted sections require a retry; completed sections remain available. An abrupt crash can lose the final unacknowledged chunk of the active section. Raw attempts are never automatically deleted.

**Retry:** prepare the affected section again if necessary, then arm and record it. Earlier successful attempts remain on disk. Joining is blocked until every section is reviewed and section file hashes still match. Joining creates another unique MP3 and checks decoding, non-silence and duration against the ordered sections.

Recordings include the waiting time between arming and playback and between playback and finishing. Silence is retained to avoid automatically cutting off speech. Background operation was part of the initial capture proof. Browser closure, logout, lid closure and sleep are unsupported. Sleep prevention is requested only during capture and released after finishing/cancelling; pre-existing Mac sleep settings are left alone.

Paragraphs are kept intact, including their original separators. A single paragraph longer than 12,000 characters is refused at preparation time; add paragraph boundaries in a new job. ChatGPT refusals, rewriting, repeats and truncation fail verification. On a mismatch, only verification metadata is saved, without the rejected reply text. Instructions inside a document are sent as quoted narration content, and a mismatching response cannot be armed.

## Validation

The native-host registration is only in the dedicated profile's `NativeMessagingHosts` directory. Its exact extension origin is the sole allowed caller. No network listener, credentials, cookies or authentication extraction is used. Browser page integration reads visible messages and fills the composer through Chrome's extension API; it can need updating if ChatGPT's UI changes. It never calls undocumented ChatGPT endpoints.

Run local checks with `python3 -m unittest -v`, `node --test test_browser.js`, `python3 -m py_compile workflow.py native_host.py install.py`, and `node --check` on the extension JavaScript files. The synthetic audio test checks conversion, cancellation, retry, concatenation and output decoding. The earlier live browser and listening checks are summarised in `VALIDATION.md`.
