#!/usr/bin/env python3
"""
Video Cutter GUI - 带实时预览的视频剪辑工具
支持进度条、时间戳显示、播放控制、键盘快捷键、片段标记和导出
"""

import os
import sys
import subprocess
import tempfile
import traceback
import logging
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QSlider, QLabel, QFileDialog, QListWidget, QListWidgetItem,
    QMessageBox, QProgressBar, QGroupBox, QLineEdit, QFrame, QDialog
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QMutex
from PyQt6.QtGui import QIcon, QKeySequence, QShortcut

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class VideoCutterError(Exception):
    """基础异常类"""
    pass


class FFmpegNotFoundError(VideoCutterError):
    """FFmpeg未找到"""
    pass


class VideoLoadError(VideoCutterError):
    """视频加载失败"""
    pass


class ExportError(VideoCutterError):
    """导出失败"""
    pass


def check_ffmpeg():
    """检查FFmpeg是否可用"""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


try:
    import cv2
except ImportError:
    print("正在安装 OpenCV...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "opencv-python", "-q"])
    import cv2

try:
    import pygame
    HAS_PYGAME = True
except ImportError:
    HAS_PYGAME = False

try:
    from PyQt6.QtMultimedia import QMediaPlayer
    from PyQt6.QtMultimediaWidgets import QVideoWidget
    HAS_QTMULTIMEDIA = True
except ImportError:
    HAS_QTMULTIMEDIA = False


class VideoThread(QThread):
    """视频帧读取线程"""
    frame_ready = pyqtSignal(object)
    error_occurred = pyqtSignal(str)
    playback_finished = pyqtSignal()

    def __init__(self, video_path):
        super().__init__()
        self.video_path = video_path
        self.cap = None
        self.running = False
        self.paused = False
        self.current_pos = 0
        self.fps = 30
        self._duration = 0
        self._mutex = QMutex()
        self._seek_pos = None

    def run(self):
        try:
            self.cap = cv2.VideoCapture(self.video_path)
            if not self.cap.isOpened():
                self.error_occurred.emit(f"无法打开视频文件: {self.video_path}")
                return

            self.fps = self.cap.get(cv2.CAP_PROP_FPS)
            frame_count = self.cap.get(cv2.CAP_PROP_FRAME_COUNT)
            if self.fps > 0:
                self._duration = int((frame_count / self.fps) * 1000)
            self.running = True

            while self.running:
                if self.paused:
                    self.msleep(10)
                    continue
                
                self._mutex.lock()
                try:
                    if self._seek_pos is not None:
                        self.cap.set(cv2.CAP_PROP_POS_MSEC, self._seek_pos)
                        self._seek_pos = None
                    
                    if self.cap and self.cap.isOpened():
                        ret, frame = self.cap.read()
                    else:
                        ret = False
                        frame = None
                finally:
                    self._mutex.unlock()
                
                if ret and frame is not None:
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    self.frame_ready.emit(frame_rgb)
                    if self.fps > 0:
                        self.msleep(int(1000 / self.fps))
                elif not ret:
                    self.paused = True
                    self._mutex.lock()
                    try:
                        if self.cap and self.cap.isOpened():
                            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    finally:
                        self._mutex.unlock()
                    self.playback_finished.emit()
        except Exception as e:
            logger.error(f"VideoThread错误: {e}\n{traceback.format_exc()}")
            self.error_occurred.emit(f"视频处理错误: {str(e)}")

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def seek(self, position):
        self._mutex.lock()
        self._seek_pos = position
        self._mutex.unlock()

    def get_current_pos(self):
        self._mutex.lock()
        try:
            if self.cap and self.cap.isOpened():
                return self.cap.get(cv2.CAP_PROP_POS_MSEC)
            return 0
        finally:
            self._mutex.unlock()

    def get_duration(self):
        return self._duration

    def stop(self):
        self.running = False
        self._mutex.lock()
        try:
            if self.cap:
                try:
                    self.cap.release()
                except Exception as e:
                    logger.warning(f"释放VideoCapture失败: {e}")
                self.cap = None
        finally:
            self._mutex.unlock()


class VideoLabel(QLabel):
    """自定义标签用于显示视频帧"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("""
            QLabel {
                background-color: #1a1a1a;
                border: 1px solid #333;
                border-radius: 4px;
            }
        """)
        self.setMinimumSize(640, 360)

    def set_frame(self, pixmap):
        if pixmap:
            scaled = pixmap.scaled(
                self.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.setPixmap(scaled)


class VideoCutterGUI(QMainWindow):
    """主窗口"""

    def __init__(self):
        super().__init__()
        self.input_video = None
        self.output_dir = None
        self.segments = []
        self.is_playing = False
        self.current_time = 0
        self.duration = 0
        self.video_thread = None
        self.frame_timer = QTimer()
        self.audio_path = None
        self._temp_audio_file = None
        self._audio_enabled = False

        if not check_ffmpeg():
            QMessageBox.critical(
                None, "错误",
                "未找到FFmpeg！请安装FFmpeg并添加到PATH环境变量。\n\n"
                "下载地址: https://ffmpeg.org/download.html"
            )
            sys.exit(1)

        if HAS_PYGAME:
            try:
                pygame.mixer.init()
                self._audio_enabled = True
            except Exception as e:
                logger.warning(f"pygame音频初始化失败: {e}")
                self._audio_enabled = False

        self.init_ui()
        self.setup_shortcuts()
        self.apply_stylesheet()

    def init_ui(self):
        """初始化UI"""
        self.setWindowTitle("Video Cutter GUI - 视频分段剪辑工具")
        self.setMinimumSize(900, 700)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # 顶部按钮栏
        top_bar = QHBoxLayout()
        self.btn_open = QPushButton("📂 打开视频")
        self.btn_open.clicked.connect(self.open_video)
        self.lbl_video_path = QLabel("未加载视频")
        self.lbl_video_path.setStyleSheet("color: #888;")
        self.lbl_video_path.setMinimumWidth(400)

        top_bar.addWidget(self.btn_open)
        top_bar.addWidget(self.lbl_video_path, 1)
        main_layout.addLayout(top_bar)

        # 视频预览区域
        self.video_label = VideoLabel()
        self.video_label.setFrameShape(QFrame.Shape.Box)
        main_layout.addWidget(self.video_label, 1)

        # 时间显示
        time_layout = QHBoxLayout()
        self.lbl_current_time = QLabel("00:00:00.00")
        self.lbl_current_time.setStyleSheet("font-family: monospace; font-size: 14px;")
        time_layout.addWidget(self.lbl_current_time)
        time_layout.addStretch()

        # 进度条
        self.progress_slider = QSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setMinimum(0)
        self.progress_slider.setMaximum(1000)
        self.progress_slider.setValue(0)
        self.progress_slider.sliderMoved.connect(self.on_sliderMoved)
        self.progress_slider.sliderPressed.connect(self.on_sliderPressed)
        self.progress_slider.sliderReleased.connect(self.on_sliderReleased)
        self.progress_slider.setEnabled(False)
        time_layout.addWidget(self.progress_slider, 1)

        time_layout.addStretch()
        self.lbl_duration = QLabel("00:00:00.00")
        self.lbl_duration.setStyleSheet("font-family: monospace; font-size: 14px;")
        time_layout.addWidget(self.lbl_duration)
        main_layout.addLayout(time_layout)

        # 播放控制栏
        controls_layout = QHBoxLayout()

        # 播放按钮
        self.btn_play = QPushButton("▶️")
        self.btn_play.setFixedSize(50, 40)
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_play.setEnabled(False)
        controls_layout.addWidget(self.btn_play)

        # 步进按钮
        self.btn_back_10 = QPushButton("⏪-10s")
        self.btn_back_10.clicked.connect(lambda: self.seek_relative(-10000))
        self.btn_back_10.setEnabled(False)
        controls_layout.addWidget(self.btn_back_10)

        self.btn_back_5 = QPushButton("⬅️-1s")
        self.btn_back_5.clicked.connect(lambda: self.seek_relative(-1000))
        self.btn_back_5.setEnabled(False)
        controls_layout.addWidget(self.btn_back_5)

        self.btn_forward_5 = QPushButton("+1s➡️")
        self.btn_forward_5.clicked.connect(lambda: self.seek_relative(1000))
        self.btn_forward_5.setEnabled(False)
        controls_layout.addWidget(self.btn_forward_5)

        self.btn_forward_10 = QPushButton("+10s⏩")
        self.btn_forward_10.clicked.connect(lambda: self.seek_relative(10000))
        self.btn_forward_10.setEnabled(False)
        controls_layout.addWidget(self.btn_forward_10)

        controls_layout.addSpacing(20)

        # 标记按钮
        self.btn_set_in = QPushButton("🟢 标记入点")
        self.btn_set_in.clicked.connect(self.set_in_point)
        self.btn_set_in.setEnabled(False)
        controls_layout.addWidget(self.btn_set_in)

        self.btn_set_out = QPushButton("🔴 标记出点")
        self.btn_set_out.clicked.connect(self.set_out_point)
        self.btn_set_out.setEnabled(False)
        controls_layout.addWidget(self.btn_set_out)

        controls_layout.addStretch()

        main_layout.addLayout(controls_layout)

        # 快捷键提示
        hint_layout = QHBoxLayout()
        hint_label = QLabel("快捷键: Space-播放/暂停 | ←/→-±1秒 | J/K/L-±10s/暂停 | I/O-设置入/出点")
        hint_label.setStyleSheet("color: #666; font-size: 11px;")
        hint_layout.addWidget(hint_label)
        main_layout.addLayout(hint_layout)

        # 片段列表
        segments_group = QGroupBox("📋 已标记的片段")
        segments_layout = QVBoxLayout()

        self.segments_list = QListWidget()
        self.segments_list.setMinimumHeight(120)
        self.segments_list.itemDoubleClicked.connect(self.edit_segment)
        self.segments_list.itemSelectionChanged.connect(self.on_segment_selection_changed)
        segments_layout.addWidget(self.segments_list)

        list_btn_layout = QHBoxLayout()
        self.btn_edit_segment = QPushButton("编辑")
        self.btn_edit_segment.clicked.connect(self.edit_segment)
        self.btn_edit_segment.setEnabled(False)
        list_btn_layout.addWidget(self.btn_edit_segment)

        self.btn_delete_segment = QPushButton("删除")
        self.btn_delete_segment.clicked.connect(self.delete_segment)
        self.btn_delete_segment.setEnabled(False)
        list_btn_layout.addWidget(self.btn_delete_segment)

        self.btn_clear_all = QPushButton("清空")
        self.btn_clear_all.clicked.connect(self.clear_all_segments)
        self.btn_clear_all.setEnabled(False)
        list_btn_layout.addWidget(self.btn_clear_all)

        list_btn_layout.addStretch()

        segments_layout.addLayout(list_btn_layout)
        segments_group.setLayout(segments_layout)
        main_layout.addWidget(segments_group)

        # 输出目录
        output_layout = QHBoxLayout()
        output_layout.addWidget(QLabel("输出目录:"))
        self.edit_output_dir = QLineEdit()
        self.edit_output_dir.setPlaceholderText("选择输出目录...")
        output_layout.addWidget(self.edit_output_dir, 1)

        self.btn_browse = QPushButton("📁 浏览")
        self.btn_browse.clicked.connect(self.browse_output_dir)
        output_layout.addWidget(self.btn_browse)

        self.btn_export = QPushButton("🎬 导出片段")
        self.btn_export.clicked.connect(self.export_segments)
        self.btn_export.setEnabled(False)
        output_layout.addWidget(self.btn_export)

        main_layout.addLayout(output_layout)

        # 进度显示
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        # 初始化定时器
        self.frame_timer.timeout.connect(self.update_frame)
        self.frame_timer.setInterval(33)  # ~30fps

    def setup_shortcuts(self):
        """设置键盘快捷键"""
        shortcuts = {
            'Space': self.toggle_play,
            'Left': lambda: self.seek_relative(-5000),
            'Right': lambda: self.seek_relative(5000),
            'J': lambda: self.seek_relative(-10000),
            'K': self.toggle_play,
            'L': lambda: self.seek_relative(10000),
            'I': self.set_in_point,
            'O': self.set_out_point,
        }

        for key, func in shortcuts.items():
            QShortcut(QKeySequence(key), self).activated.connect(func)

    def apply_stylesheet(self):
        """应用样式"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2b2b2b;
            }
            QLabel {
                color: #e0e0e0;
            }
            QPushButton {
                background-color: #3a3a3a;
                color: #ffffff;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 6px 12px;
                min-width: 60px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
            }
            QPushButton:pressed {
                background-color: #2a2a2a;
            }
            QPushButton:disabled {
                background-color: #2b2b2b;
                color: #666;
            }
            QSlider::groove:horizontal {
                border: 1px solid #555;
                height: 8px;
                background: #1a1a1a;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #4a90d9;
                width: 3px;
                margin: -6px 0;
                border-radius: 0px;
            }
            QSlider::handle:horizontal:hover {
                background: #5aa0e9;
            }
            QListWidget {
                background-color: #1e1e1e;
                border: 1px solid #333;
                color: #e0e0e0;
            }
            QListWidget::item:selected {
                background-color: #4a90d9;
            }
            QGroupBox {
                color: #e0e0e0;
                border: 1px solid #444;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QLineEdit {
                background-color: #1e1e1e;
                color: #e0e0e0;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QProgressBar {
                border: 1px solid #444;
                border-radius: 4px;
                text-align: center;
                background-color: #1e1e1e;
            }
            QProgressBar::chunk {
                background-color: #4a90d9;
            }
        """)

    def open_video(self):
        """打开视频文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择视频文件", "",
            "视频文件 (*.mp4 *.avi *.mkv *.mov *.flv *.wmv *.webm);;所有文件 (*.*)"
        )

        if file_path:
            self.input_video = file_path
            self.lbl_video_path.setText(file_path)
            self.load_video(file_path)

    def load_video(self, video_path):
        """加载视频"""
        try:
            if not os.path.exists(video_path):
                raise VideoLoadError(f"视频文件不存在: {video_path}")
            
            if not os.access(video_path, os.R_OK):
                raise VideoLoadError(f"无法读取视频文件: {video_path}")

            if self.video_thread:
                self.video_thread.stop()
                self.video_thread.wait(1000)
                self.video_thread = None

            self.stop_audio()

            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise VideoLoadError(f"OpenCV无法打开视频: {video_path}")
            
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            cap.release()

            if fps <= 0 or frame_count <= 0:
                raise VideoLoadError("视频文件无效: 无法获取帧率或帧数")

            self.duration = int((frame_count / fps) * 1000)

            self.video_thread = VideoThread(video_path)
            self.video_thread.frame_ready.connect(self.display_frame)
            self.video_thread.error_occurred.connect(self.on_video_error)
            self.video_thread.playback_finished.connect(self.on_playback_finished)
            self.video_thread.start()

            self.lbl_duration.setText(self.format_time(self.duration))
            self.enable_controls(True)
            self.progress_slider.setEnabled(True)

            self.prepare_audio(video_path)
            self.toggle_play()
            
        except VideoLoadError as e:
            logger.error(f"视频加载失败: {e}")
            QMessageBox.warning(self, "加载失败", str(e))
            self.enable_controls(False)
            self.progress_slider.setEnabled(False)
        except Exception as e:
            logger.error(f"视频加载异常: {e}\n{traceback.format_exc()}")
            QMessageBox.critical(self, "错误", f"加载视频时发生错误:\n{str(e)}")
            self.enable_controls(False)
            self.progress_slider.setEnabled(False)

    def on_video_error(self, error_msg):
        """视频线程错误回调"""
        logger.error(f"视频线程错误: {error_msg}")
        QMessageBox.warning(self, "视频错误", error_msg)

    def on_playback_finished(self):
        """视频播放完成回调"""
        if self.is_playing:
            self.is_playing = False
            self.btn_play.setText("▶️")
            self.frame_timer.stop()
        
        self.current_time = 0
        self.lbl_current_time.setText(self.format_time(0))
        self.progress_slider.setValue(0)
        
        if self._audio_enabled and HAS_PYGAME:
            try:
                if pygame.mixer.music.get_busy():
                    pygame.mixer.music.stop()
            except Exception:
                pass

    def prepare_audio(self, video_path):
        """从视频中提取音频"""
        if not self._audio_enabled or not HAS_PYGAME:
            return

        try:
            self._temp_audio_file = tempfile.NamedTemporaryFile(
                suffix=".wav", delete=False
            )
            self.audio_path = self._temp_audio_file.name
            self._temp_audio_file.close()

            cmd = [
                "ffmpeg", "-y", "-i", video_path,
                "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
                self.audio_path
            ]
            result = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30
            )
            if result.returncode != 0:
                logger.warning(f"音频提取失败: {result.stderr.decode('utf-8', errors='ignore')}")
                self._cleanup_audio()
                return

            pygame.mixer.music.load(self.audio_path)
            logger.info("音频提取成功")
        except subprocess.TimeoutExpired:
            logger.warning("音频提取超时")
            self._cleanup_audio()
        except Exception as e:
            logger.warning(f"音频准备失败: {e}")
            self._cleanup_audio()

    def _cleanup_audio(self):
        """清理音频资源"""
        if HAS_PYGAME:
            try:
                if pygame.mixer.music.get_busy():
                    pygame.mixer.music.stop()
            except Exception:
                pass
        
        if self.audio_path and os.path.exists(self.audio_path):
            try:
                os.remove(self.audio_path)
            except Exception as e:
                logger.debug(f"删除临时音频失败: {e}")
        
        self.audio_path = None
        if self._temp_audio_file:
            self._temp_audio_file = None

    def stop_audio(self):
        """停止音频播放"""
        self._cleanup_audio()

    def display_frame(self, frame):
        """显示视频帧"""
        from PyQt6.QtGui import QImage, QPixmap
        h, w, ch = frame.shape
        bytes_per_line = ch * w
        qt_image = QImage(frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_image)

        # 保持宽高比缩放
        scaled_pixmap = pixmap.scaled(
            self.video_label.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.video_label.setPixmap(scaled_pixmap)

    def update_frame(self):
        """更新帧（定时器触发）"""
        if not self.video_thread or not self.video_thread.cap:
            return

        current_pos = self.video_thread.get_current_pos()
        if current_pos > 0:
            self.current_time = current_pos
            self.lbl_current_time.setText(self.format_time(current_pos))

            # 更新进度条
            if self.duration > 0:
                progress = int((current_pos / self.duration) * 1000)
                self.progress_slider.setValue(progress)

    def on_sliderMoved(self, value):
        """进度条拖动"""
        if self.duration > 0:
            target_time = int((value / 1000) * self.duration)
            self.lbl_current_time.setText(self.format_time(target_time))
            self.current_time = target_time
            if self.video_thread:
                self.video_thread.seek(target_time)
            if self._audio_enabled and HAS_PYGAME and self.audio_path:
                try:
                    if pygame.mixer.music.get_busy():
                        pos_sec = target_time / 1000.0
                        pygame.mixer.music.set_pos(pos_sec)
                except Exception as e:
                    logger.debug(f"音频跳转失败: {e}")

    def on_sliderPressed(self):
        """进度条按下"""
        self.was_playing = self.is_playing
        if self.is_playing:
            self.toggle_play()

    def on_sliderReleased(self):
        """进度条释放"""
        if hasattr(self, 'was_playing') and self.was_playing:
            self.toggle_play()

    def toggle_play(self):
        """切换播放/暂停"""
        self.is_playing = not self.is_playing

        if self.is_playing:
            self.btn_play.setText("⏸️")
            self.frame_timer.start()
            if self.video_thread:
                self.video_thread.resume()
            if self._audio_enabled and HAS_PYGAME and self.audio_path:
                try:
                    pygame.mixer.music.stop()
                    pos_sec = self.current_time / 1000.0
                    pygame.mixer.music.play()
                    pygame.mixer.music.set_pos(pos_sec)
                except Exception as e:
                    logger.debug(f"音频播放失败: {e}")
        else:
            self.btn_play.setText("▶️")
            self.frame_timer.stop()
            if self.video_thread:
                self.video_thread.pause()
            if self._audio_enabled and HAS_PYGAME:
                try:
                    if pygame.mixer.music.get_busy():
                        pygame.mixer.music.pause()
                except Exception as e:
                    logger.debug(f"音频暂停失败: {e}")

    def seek_relative(self, delta_ms):
        """相对跳转"""
        if self.duration <= 0:
            return

        new_time = max(0, min(self.duration, self.current_time + delta_ms))
        self.current_time = new_time
        self.lbl_current_time.setText(self.format_time(new_time))

        if self.video_thread:
            self.video_thread.seek(new_time)

        if self._audio_enabled and HAS_PYGAME and self.audio_path:
            try:
                pos_sec = new_time / 1000.0
                pygame.mixer.music.set_pos(pos_sec)
            except Exception as e:
                logger.debug(f"音频跳转失败: {e}")

        if self.duration > 0:
            progress = int((new_time / self.duration) * 1000)
            self.progress_slider.setValue(progress)

    def enable_controls(self, enabled):
        """启用/禁用控制按钮"""
        self.btn_play.setEnabled(enabled)
        self.btn_back_10.setEnabled(enabled)
        self.btn_back_5.setEnabled(enabled)
        self.btn_forward_5.setEnabled(enabled)
        self.btn_forward_10.setEnabled(enabled)
        self.btn_set_in.setEnabled(enabled)
        self.btn_set_out.setEnabled(enabled)

    def set_in_point(self):
        """设置入点"""
        start_time = self.current_time
        self.in_point = start_time
        self.lbl_current_time.setText(f"入点: {self.format_time(start_time)}")
        # 2秒后恢复
        QTimer.singleShot(2000, lambda: self.lbl_current_time.setText(self.format_time(self.current_time)))

    def set_out_point(self):
        """设置出点"""
        if not hasattr(self, 'in_point'):
            QMessageBox.warning(self, "提示", "请先设置入点 (按 I 键)")
            return

        end_time = self.current_time
        if end_time <= self.in_point:
            QMessageBox.warning(self, "提示", "出点必须大于入点")
            return

        segment = (self.in_point, end_time)
        self.segments.append(segment)
        self.update_segments_list()
        self.btn_export.setEnabled(True)
        self.btn_edit_segment.setEnabled(True)
        self.btn_clear_all.setEnabled(True)

    def update_segments_list(self):
        """更新片段列表"""
        self.segments_list.clear()
        for i, (start, end) in enumerate(self.segments, 1):
            item_text = f"#{i}  {self.format_time(start)} - {self.format_time(end)}"
            item = QListWidgetItem(item_text)
            self.segments_list.addItem(item)

    def on_segment_selection_changed(self):
        """片段选择变化"""
        has_selection = self.segments_list.currentRow() >= 0
        self.btn_edit_segment.setEnabled(has_selection)
        self.btn_delete_segment.setEnabled(has_selection)

    def edit_segment(self):
        """编辑选中的片段"""
        current_row = self.segments_list.currentRow()
        if current_row < 0:
            return

        start, end = self.segments[current_row]

        dialog = QDialog(self)
        dialog.setWindowTitle(f"编辑片段 #{current_row + 1}")
        dialog.setModal(True)
        dialog.setMinimumWidth(300)

        layout = QVBoxLayout(dialog)

        form_layout = QHBoxLayout()
        form_layout.addWidget(QLabel("开始:"))
        start_edit = QLineEdit(self.format_time(start))
        start_edit.setStyleSheet("font-family: monospace;")
        form_layout.addWidget(start_edit)
        form_layout.addWidget(QLabel("结束:"))
        end_edit = QLineEdit(self.format_time(end))
        end_edit.setStyleSheet("font-family: monospace;")
        form_layout.addWidget(end_edit)
        layout.addLayout(form_layout)

        hint = QLabel("格式: HH:MM:SS.ss (如 00:01:30.50)")
        hint.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(hint)

        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("确定")
        btn_cancel = QPushButton("取消")
        btn_layout.addStretch()
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        def parse_time_str(s):
            s = s.strip()
            parts = s.split(":")
            if len(parts) == 3:
                h, m, sec = parts
                return int(float(h) * 3600000 + float(m) * 60000 + float(sec) * 1000)
            elif len(parts) == 2:
                m, sec = parts
                return int(float(m) * 60000 + float(sec) * 1000)
            else:
                return int(float(s) * 1000)

        def on_ok():
            try:
                new_start = parse_time_str(start_edit.text())
                new_end = parse_time_str(end_edit.text())
                if new_end <= new_start:
                    QMessageBox.warning(dialog, "错误", "结束时间必须大于开始时间")
                    return
                if new_start < 0 or new_end > self.duration:
                    QMessageBox.warning(dialog, "错误", f"时间超出范围 (0 - {self.format_time(self.duration)})")
                    return
                self.segments[current_row] = (new_start, new_end)
                self.update_segments_list()
                dialog.accept()
            except ValueError as e:
                QMessageBox.warning(dialog, "格式错误", f"时间格式无效: {e}")

        btn_ok.clicked.connect(on_ok)
        btn_cancel.clicked.connect(dialog.reject)
        dialog.exec()

    def delete_segment(self):
        """删除选中的片段"""
        current_row = self.segments_list.currentRow()
        if current_row >= 0:
            self.segments.pop(current_row)
            self.update_segments_list()
            self.on_segment_selection_changed()

        self.btn_export.setEnabled(len(self.segments) > 0)
        self.btn_clear_all.setEnabled(len(self.segments) > 0)

    def clear_all_segments(self):
        """清空所有片段"""
        if len(self.segments) > 0:
            reply = QMessageBox.question(
                self, "确认", "确定要清空所有已标记的片段吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.segments.clear()
                self.update_segments_list()
                self.btn_export.setEnabled(False)
                self.btn_edit_segment.setEnabled(False)
                self.btn_clear_all.setEnabled(False)

    def browse_output_dir(self):
        """选择输出目录"""
        dir_path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if dir_path:
            self.output_dir = dir_path
            self.edit_output_dir.setText(dir_path)

    def export_segments(self):
        """导出视频片段"""
        if not self.segments:
            QMessageBox.warning(self, "提示", "没有可导出的片段")
            return

        if not self.input_video:
            QMessageBox.warning(self, "提示", "请先打开视频文件")
            return

        if not self.output_dir:
            self.browse_output_dir()

        if not self.output_dir:
            return

        try:
            if not os.path.exists(self.output_dir):
                os.makedirs(self.output_dir)
            if not os.access(self.output_dir, os.W_OK):
                raise ExportError(f"输出目录不可写: {self.output_dir}")
        except ExportError:
            raise
        except Exception as e:
            raise ExportError(f"创建输出目录失败: {e}")

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        QApplication.processEvents()

        total = len(self.segments)
        base_name = os.path.splitext(os.path.basename(self.input_video))[0]
        success_count = 0
        failed_segments = []

        for idx, (start, end) in enumerate(self.segments, 1):
            start_sec = start / 1000.0
            end_sec = end / 1000.0

            output_file = self.get_unique_filename(
                self.output_dir,
                f"{base_name}_clip_{idx}",
                ".mp4"
            )

            cmd = [
                "ffmpeg", "-y",
                "-ss", str(start_sec),
                "-to", str(end_sec),
                "-i", self.input_video,
                "-c", "copy",
                output_file
            ]

            try:
                result = subprocess.run(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60
                )
                if result.returncode == 0:
                    success_count += 1
                    logger.info(f"导出片段 {idx} 成功: {output_file}")
                else:
                    error_msg = result.stderr.decode('utf-8', errors='ignore')
                    failed_segments.append((idx, error_msg[:200] if len(error_msg) > 200 else error_msg))
                    logger.error(f"导出片段 {idx} 失败: {error_msg}")
            except subprocess.TimeoutExpired:
                failed_segments.append((idx, "导出超时"))
                logger.error(f"导出片段 {idx} 超时")
            except Exception as e:
                failed_segments.append((idx, str(e)))
                logger.error(f"导出片段 {idx} 异常: {e}")

            progress = int((idx / total) * 100)
            self.progress_bar.setValue(progress)
            QApplication.processEvents()

        self.progress_bar.setVisible(False)

        if failed_segments:
            failed_msg = "\n".join([f"片段#{idx}: {msg}" for idx, msg in failed_segments[:3]])
            if len(failed_segments) > 3:
                failed_msg += f"\n... 还有 {len(failed_segments) - 3} 个失败"
            QMessageBox.warning(
                self, "导出完成（部分失败）",
                f"成功: {success_count}/{total}\n失败: {len(failed_segments)}\n\n"
                f"失败详情:\n{failed_msg}\n\n输出目录: {self.output_dir}"
            )
        else:
            QMessageBox.information(
                self, "导出完成",
                f"成功导出 {success_count} 个片段到:\n{self.output_dir}"
            )

    @staticmethod
    def format_time(ms):
        """格式化时间显示"""
        total_seconds = int(ms / 1000)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        milliseconds = int(ms % 1000) // 10
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:02d}"

    @staticmethod
    def get_unique_filename(output_dir, base_name, extension):
        """生成唯一的文件名"""
        filename = f"{base_name}{extension}"
        output_file = os.path.join(output_dir, filename)

        if not os.path.exists(output_file):
            return output_file

        i = 1
        while True:
            filename = f"{base_name}_{i}{extension}"
            output_file = os.path.join(output_dir, filename)
            if not os.path.exists(output_file):
                return output_file
            i += 1

    def closeEvent(self, event):
        """窗口关闭事件"""
        try:
            if self.video_thread:
                self.video_thread.stop()
                if not self.video_thread.wait(3000):
                    logger.warning("VideoThread未能正常停止")
            self.stop_audio()
        except Exception as e:
            logger.error(f"关闭时清理资源失败: {e}")
        finally:
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Video Cutter GUI")

    # 设置应用程序样式
    app.setStyle('Fusion')

    window = VideoCutterGUI()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
