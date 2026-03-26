# CLIP_RECORDING_LOG.md

## Iteration 10: Pre/Post Event Video Clip Recording

### Status
Implemented and active. Validated to gracefully drop upon Codec failures.

### Architecture
- **Ring Buffer**: Implemented inside `ClipRecorder`. Stores a continuous sub-sampled (by target FPS) rolling history of N seconds using `collections.deque`.
- **Pre-buffer Extraction**: Upon target event emission, `on_event` fetches the entire memory-bound `buffer` and flushes it to a newly created temporary writer instance immediately.
- **Post-event Subsampling**: After an event happens, an active `ClipJob` keeps storing future frames arriving from `feed_frame` until the target post-event time duration bounds are hit.
- **Main Loop integration**: `main.py` explicitly forwards frames out of bounds of the skip-frame inference logic. Completed clip paths are flushed to DB natively on main thread so that it plays nicely with the synchronous sqlite SQLiteEventRepository singleton limitation.
- **Output Structure**: Clips are saved in `data/clips/YYYY-MM-DD/<event_id>.<ext>`.

### Limitations
- Clip writing happens **synchronously through continuous main loop execution**, chunking frame writes frame-by-frame per cycle. It is NOT truly asynchronous. Write time scaling with huge clip durations might cause small intermittent lags, but since writing MP4 frames uses incremental chunks to the FS it behaves reliably without big heap spikes.
- Currently, overlapping clips might duplicate disk space. We decided to favor redundancy per event.
