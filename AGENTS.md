# Video Cutter

Python GUI tool for extracting video segments using FFmpeg.

## Requirements

- Python 3.11
- FFmpeg (must be on PATH)

## Run

```
python video_cutter_GUI_v1.py   # tkinter (no pip deps)
python video_cutter_GUI_v2.py   # PyQt6 (pip install PyQt6 opencv-python pygame)
```

## Versions

- `video_cutter_GUI_v1.py` - tkinter GUI, logs to `video_cutter.log` (cleared each run)
- `video_cutter_GUI_v2.py` - PyQt6 GUI with video preview, auto-installs opencv-python if missing, checks FFmpeg at startup
- `video_cutter.py` - CLI/library only

## Notes

- No tests
- FFmpeg uses `-c copy` (stream copy, no re-encoding)
- Both versions log to `video_cutter.log` (cleared each run)
