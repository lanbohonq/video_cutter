# Video Cutter

一个基于 Python 和 FFmpeg 的视频分段剪辑工具，提供两个版本的图形界面，支持快速提取视频中的多个片段。

## 功能特性

- 🎬 **视频预览** - 实时预览视频内容，精确定位剪辑点
- ⏱️ **时间标记** - 通过快捷键或按钮快速标记入点/出点
- 📝 **片段管理** - 支持添加、编辑、删除、清空片段
- 🚀 **快速导出** - 使用 FFmpeg 流复制模式，无需重新编码
- 🎹 **快捷键支持** - 完整的键盘快捷键提升操作效率
- 🌙 **深色主题** - 现代化的深色界面设计

## 系统要求

- **Python**: 3.11+
- **FFmpeg**: 必须安装并添加到系统 PATH 环境变量

### 安装 FFmpeg

**Windows:**
```bash
# 使用 winget
winget install ffmpeg

# 或使用 scoop
scoop install ffmpeg

# 或从官网下载: https://ffmpeg.org/download.html
```

**macOS:**
```bash
brew install ffmpeg
```

**Linux:**
```bash
sudo apt install ffmpeg  # Debian/Ubuntu
sudo dnf install ffmpeg  # Fedora
```

## 安装

```bash
git clone https://github.com/lanbohonq/video_cutter.git
cd video_cutter
```

## 使用方法

### 版本说明

| 文件 | 界面 | 依赖 | 特点 |
|------|------|------|------|
| `video_cutter_GUI_v1.py` | tkinter | 无（标准库） | 轻量级，适合快速使用 |
| `video_cutter_GUI_v2.py` | PyQt6 | PyQt6, opencv-python, pygame | 带视频预览，功能完整 |
| `video_cutter.py` | 命令行 | 无 | 可作为库调用 |

### 运行 v1 (tkinter 版本)

```bash
python video_cutter_GUI_v1.py
```

无需安装额外依赖，使用 Python 标准库的 tkinter 构建。

**特点:**
- 轻量级，启动快
- 支持多种时间格式输入
- 日志记录到 `video_cutter.log`

### 运行 v2 (PyQt6 版本)

```bash
# 安装依赖
pip install PyQt6 opencv-python pygame

# 运行
python video_cutter_GUI_v2.py
```

**特点:**
- 实时视频预览
- 音频播放支持
- 可视化时间轴拖动
- 完整的快捷键支持
- 片段双击编辑

### 作为库使用

```python
from video_cutter import cut_video_segments

segments = [
    ("00:00:10", "00:00:20"),  # HH:MM:SS 格式
    ("01:00", "01:30"),        # MM:SS 格式
    (90, 120),                  # 秒数
]

cut_video_segments(
    input_video="input.mp4",
    output_dir="./output",
    segments=segments
)
```

## 操作指南

### v2 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Space` | 播放/暂停 |
| `←` / `→` | 后退/前进 5 秒 |
| `J` | 后退 10 秒 |
| `K` | 暂停 |
| `L` | 前进 10 秒 |
| `I` | 标记入点 |
| `O` | 标记出点 |

### 时间格式支持

支持以下时间格式输入:

- `HH:MM:SS` - 小时:分钟:秒 (如 `01:30:45`)
- `MM:SS` - 分钟:秒 (如 `05:30`)
- 秒数 - 纯数字 (如 `90` 表示 90 秒)
- `HH:MM:SS.ss` - 带毫秒 (如 `00:01:30.50`)

### 工作流程

1. **打开视频** - 点击"打开视频"按钮选择视频文件
2. **预览定位** - 拖动进度条或使用快捷键定位到目标位置
3. **标记片段** - 按 `I` 标记入点，移动到结束位置后按 `O` 标记出点
4. **管理片段** - 可双击编辑片段时间，或删除不需要的片段
5. **设置输出** - 选择输出目录
6. **导出** - 点击"导出片段"开始处理

## 技术细节

### FFmpeg 参数

导出时使用以下 FFmpeg 命令:

```bash
ffmpeg -y -ss <start> -to <end> -i <input> -c copy <output>
```

- `-c copy` - 流复制模式，不重新编码，速度极快
- `-y` - 覆盖已存在的输出文件
- `-ss` / `-to` - 精确时间定位

### 文件命名

输出文件自动命名格式: `<原文件名>_clip_<序号>.mp4`

如文件已存在，自动追加序号: `<原文件名>_clip_<序号>_1.mp4`

### 日志

- v1 版本日志保存到 `video_cutter.log`，每次运行清空
- v2 版本日志输出到控制台

## 项目结构

```
video_cutter/
├── video_cutter_GUI_v1.py   # tkinter 版本 GUI
├── video_cutter_GUI_v2.py   # PyQt6 版本 GUI (推荐)
├── video_cutter.py          # 核心函数库
├── AGENTS.md                # 开发者指南
└── README.md                # 本文档
```

## 常见问题

### FFmpeg 未找到

启动 v2 时提示 "未找到FFmpeg":

1. 确认 FFmpeg 已安装
2. 确认 `ffmpeg` 命令在 PATH 中可用
3. Windows 用户可能需要重启终端或 IDE

### 视频无法打开

- 确认视频文件未被其他程序占用
- 确认视频格式受支持 (mp4, avi, mkv, mov, flv, wmv, webm)
- 尝试用其他播放器验证视频文件是否损坏

### 导出片段时长不精确

由于使用流复制模式 (`-c copy`)，导出片段的时间点可能会对齐到最近的关键帧。如需精确切割，需要移除 `-c copy` 参数进行重新编码（会显著降低速度）。
