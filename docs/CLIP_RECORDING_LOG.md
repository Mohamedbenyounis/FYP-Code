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

## Iteration 12c: Lifecycle-Aware Clip Recording

### Status
Implemented and active. Resolves the flaw of static, artificially limited 5-second video output clips.

### Dynamic Overhaul
- **Track Lifecycle Binding**: Video recordings are no longer fixed at a hardcoded post-event length. Clips are now dynamically bound to `Event.track_key`.
- **Active Mode**: When an event triggers, `ClipRecorder` establishes an `'active'` job which continues recording new, incoming camera frames perpetually as long as the person stays in frame.
- **Track State Observation**: The secondary processing daemon (`main.py`) actively propagates Face State snapshots (e.g. `'ACTIVE'`, `'COOLDOWN'`) to `clip_recorder.update_track_states()`.
- **Post-Tail Mode**: When an individual finally deserts the frame (losing their `'ACTIVE'` state), their video clip enters `'tail'` mode. It initiates a rigid, N-second countdown to flush the final 3.0 seconds post-exit.
- **Disk Cap Safety Ceiling**: To safeguard the host environment against infinite video allocation (from stationary threats), `config.CLIP_MAX_DURATION_SECONDS` immediately forces closure of any video recording reaching a predefined chronological cap regardless of state. Standard defaults cap clips effectively around one minute.
