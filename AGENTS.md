# Video Cutter

Python GUI tool for extracting video segments using FFmpeg.

## Requirements

- Python 3.11
- FFmpeg (must be on PATH, or use bundled `bin/ffmpeg.exe`)

## Run

```
python src/video_cutter_GUI_v1.py   # tkinter (no pip deps)
python src/video_cutter_GUI_v2.py   # PyQt6 (pip install PyQt6 opencv-python pygame)
```

## Project Structure

```
src/
  video_cutter.py          # CLI/library (import `cut_video_segments`)
  video_cutter_GUI_v1.py   # tkinter GUI
  video_cutter_GUI_v2.py   # PyQt6 GUI with video preview
assets/
  icon.ico                 # application icon
bin/
  ffmpeg.exe               # bundled FFmpeg (optional)
```

## Notes

- No tests
- FFmpeg uses `-c copy` (stream copy, no re-encoding)
- Both GUIs log to `video_cutter.log` in project root (cleared each run)
