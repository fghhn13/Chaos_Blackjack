# Casino sound sources

`kenney/` contains the 54 original `.ogg` clips from the `Audio/` directory of
[Kenney Casino Audio](https://kenney.nl/assets/casino-audio), version 1.1.
They are CC0, copied without editing or transcoding. The original license is
`kenney/License.txt`; source URL, archive SHA-256 and individual byte counts and
hashes are in `kenney/source.json`.

`cues.json` assigns five game meanings to existing clips: deal, chips, win, lose
and chaos. Win uses chip stacking; lose uses card sweeping. The source contains
casino foley rather than musical result jingles. Unused original clips remain
available for later mapping, under the same license.

The website advertises 50 sounds; the downloaded version 1.1 archive contains
54 source OGG clips. This manifest describes the files actually imported.

Check locally without opening an audio device:

```bash
python -m chaos_blackjack.audio validate
python -m chaos_blackjack.audio list
```

Integration details: [Audio guide](../../../docs/AUDIO_GUIDE.md).
