# Video Cutter

Python GUI tool for extracting video segments using FFmpeg.

## Requirements

- Python 3.11
- FFmpeg (must be installed and available on PATH)

## Run

```
python video_cutter_GUI_v1.py
```

## Versions

- `video_cutter_GUI_v1.py` - tkinter GUI (standard library, no pip dependencies)
- `video_cutter_GUI_v2.py` - PyQt6 GUI with video preview (requires `pip install PyQt6 opencv-python pygame`)
- `video_cutter.py` - CLI/library functions only

## Notes

- No tests exist in this repo
- FFmpeg uses `-c copy` for fast stream copy without re-encoding
- v1 logs to `video_cutter.log` (cleared on each run)
- v2 auto-installs opencv-python if missing
- v2 checks FFmpeg availability at startup and exits with error if not found
- v2 uses tempfile for audio extraction (auto-cleanup on close)
