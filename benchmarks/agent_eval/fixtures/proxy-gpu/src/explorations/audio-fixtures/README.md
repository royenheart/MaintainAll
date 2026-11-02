# Native MP3 fixture

`steady-tone.mp3` is an original, generated 220 Hz sine wave, not an artist
recording. It exercises MP3 preloading, first playback, native Web Audio output
and pause/resume. Unlike the existing data-URL WAV fixtures, it is loaded over
HTTP as a bundled asset.

Regenerate from the repository root with FFmpeg:

```sh
ffmpeg -v error -f lavfi -i 'sine=frequency=220:duration=12' \
  -map_metadata -1 -codec:a libmp3lame -b:a 192k -ar 44100 -ac 2 \
  proxy/src/explorations/audio-fixtures/steady-tone.mp3
```

The fixture is only imported by a test story. It is never substituted for the
selected soundtrack.
