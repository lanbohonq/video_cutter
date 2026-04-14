#!/usr/bin/env python3
"""
视频分割GUI工具
基于FFmpeg的视频片段提取工具
"""

import os
import subprocess
import threading
import logging
from datetime import timedelta
from tkinter import (
    Tk, StringVar, IntVar, DoubleVar, Text,
    ttk, filedialog, messagebox, simpledialog,
    Listbox, Scrollbar, VERTICAL, END, ACTIVE, Toplevel
)

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "video_cutter.log")

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        filename=LOG_FILE,
        filemode='w',
        encoding='utf-8'
    )

def parse_time(t):
    """
    支持:
    - 秒 (int/float)
    - "HH:MM:SS"
    - "MM:SS"
    """
    if isinstance(t, (int, float)):
        return str(int(t))
    parts = list(map(float, t.split(":")))
    if len(parts) == 3:
        h, m, s = parts
    elif len(parts) == 2:
        h, m, s = 0, parts[0], parts[1]
    else:
        raise ValueError(f"时间格式错误: {t}")
    total_seconds = int(timedelta(hours=h, minutes=m, seconds=s).total_seconds())
    return str(total_seconds)


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


def cut_video_segments(input_video, output_dir, segments, progress_callback=None):
    """执行视频分割"""
    logging.info(f"开始处理视频: {input_video}")
    logging.info(f"输出目录: {output_dir}")
    logging.info(f"共 {len(segments)} 个片段")
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        logging.info(f"创建输出目录: {output_dir}")

    base_name = os.path.splitext(os.path.basename(input_video))[0]
    results = []

    for idx, (start, end) in enumerate(segments, 1):
        start_sec = parse_time(start)
        end_sec = parse_time(end)
        output_file = get_unique_filename(output_dir, f"{base_name}_clip_{idx}", ".mp4")

        cmd = [
            "ffmpeg",
            "-y",
            "-ss", start_sec,
            "-to", end_sec,
            "-i", input_video,
            "-c", "copy",
            output_file
        ]

        logging.info(f"处理片段 {idx}: {start} -> {end}")
        logging.info(f"FFmpeg命令: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        if result.returncode == 0:
            results.append((idx, True, output_file))
            logging.info(f"片段 {idx} 处理成功: {output_file}")
        else:
            error_msg = result.stderr.decode('utf-8', errors='ignore')
            results.append((idx, False, error_msg))
            logging.error(f"片段 {idx} 处理失败: {error_msg}")

        if progress_callback:
            progress_callback(idx, len(segments))

    logging.info(f"处理完成，成功: {sum(1 for _, ok, _ in results if ok)}，失败: {sum(1 for _, ok, _ in results if not ok)}")
    return results


class VideoCutterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("视频分割工具")
        self.root.geometry("900x700")
        self.root.resizable(True, True)

        # 设置样式
        self.style = ttk.Style()
        self.style.theme_use('clam')

        # 变量
        self.input_video = StringVar()
        self.output_dir = StringVar()
        self.segments = []  # [(start, end, label), ...]
        self.is_processing = False

        # 创建界面
        self.create_widgets()

        # 设置默认输出目录
        default_output = os.path.join(os.path.expanduser("~"), "Videos", "VideoCutter")
        if os.path.exists(os.path.dirname(default_output)):
            self.output_dir.set(default_output)
        else:
            self.output_dir.set(os.path.join(os.path.expanduser("~"), "Videos"))

    def create_widgets(self):
        """创建所有界面组件"""
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill='both', expand=True)

        # === 文件选择区域 ===
        file_frame = ttk.LabelFrame(main_frame, text="文件选择", padding="10")
        file_frame.pack(fill='x', pady=(0, 10))

        # 输入视频
        input_frame = ttk.Frame(file_frame)
        input_frame.pack(fill='x', pady=5)

        ttk.Label(input_frame, text="输入视频:").pack(side='left')
        ttk.Entry(input_frame, textvariable=self.input_video, width=50).pack(side='left', padx=5)
        ttk.Button(input_frame, text="浏览...", command=self.browse_input).pack(side='left')
        ttk.Button(input_frame, text="清空", command=lambda: self.input_video.set("")).pack(side='left', padx=5)

        # 输出目录
        output_frame = ttk.Frame(file_frame)
        output_frame.pack(fill='x', pady=5)

        ttk.Label(output_frame, text="输出目录:").pack(side='left')
        ttk.Entry(output_frame, textvariable=self.output_dir, width=50).pack(side='left', padx=5)
        ttk.Button(output_frame, text="浏览...", command=self.browse_output).pack(side='left')

        # === 片段管理区域 ===
        segment_frame = ttk.LabelFrame(main_frame, text="视频片段 (格式: HH:MM:SS 或 MM:SS 或 秒数)", padding="10")
        segment_frame.pack(fill='both', expand=True, pady=(0, 10))

        # 片段列表和滚动条
        list_frame = ttk.Frame(segment_frame)
        list_frame.pack(fill='both', expand=True)

        scrollbar = Scrollbar(list_frame, orient=VERTICAL)
        self.segment_listbox = Listbox(list_frame, yscrollcommand=scrollbar.set, height=10)
        scrollbar.config(command=self.segment_listbox.yview)
        scrollbar.pack(side='right', fill='y')
        self.segment_listbox.pack(side='left', fill='both', expand=True)

        # 片段输入区域
        input_segment_frame = ttk.Frame(segment_frame)
        input_segment_frame.pack(fill='x', pady=10)

        # 开始时间
        ttk.Label(input_segment_frame, text="开始时间:").grid(row=0, column=0, padx=5, pady=5, sticky='e')
        self.start_entry = ttk.Entry(input_segment_frame, width=15)
        self.start_entry.grid(row=0, column=1, padx=5, pady=5)

        # 结束时间
        ttk.Label(input_segment_frame, text="结束时间:").grid(row=0, column=2, padx=5, pady=5, sticky='e')
        self.end_entry = ttk.Entry(input_segment_frame, width=15)
        self.end_entry.grid(row=0, column=3, padx=5, pady=5)

        # 添加片段按钮
        btn_frame = ttk.Frame(segment_frame)
        btn_frame.pack(fill='x', pady=5)

        ttk.Button(btn_frame, text="添加片段", command=self.add_segment).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="添加多个...", command=self.add_multiple_segments).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="编辑选中", command=self.edit_segment).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="删除选中", command=self.delete_segment).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="清空全部", command=self.clear_all_segments).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="↑ 上移", command=lambda: self.move_segment(-1)).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="↓ 下移", command=lambda: self.move_segment(1)).pack(side='left', padx=5)

        # 快速添加按钮
        quick_frame = ttk.LabelFrame(segment_frame, text="快速添加 (逗号分隔)")
        quick_frame.pack(fill='x', pady=5)

        ttk.Label(quick_frame, text="多个时间对 (格式: 0:00-0:30, 1:00-1:30):").pack(side='left', padx=5)
        self.quick_entry = ttk.Entry(quick_frame, width=40)
        self.quick_entry.pack(side='left', padx=5)
        ttk.Button(quick_frame, text="添加", command=self.quick_add_segments).pack(side='left', padx=5)

        # === 进度和状态区域 ===
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(fill='x', pady=(0, 10))

        self.progress = ttk.Progressbar(status_frame, mode='determinate')
        self.progress.pack(fill='x', pady=5)

        self.status_label = ttk.Label(status_frame, text="就绪")
        self.status_label.pack()

        # === 操作按钮 ===
        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill='x')

        self.start_button = ttk.Button(
            action_frame,
            text="▶ 开始分割",
            command=self.start_processing
        )
        self.start_button.pack(side='left', padx=5, ipadx=20)

        ttk.Button(
            action_frame,
            text="打开输出目录",
            command=self.open_output_dir
        ).pack(side='left', padx=5)

        ttk.Button(
            action_frame,
            text="退出",
            command=self.root.quit
        ).pack(side='right', padx=5)

        # 绑定双击事件
        self.segment_listbox.bind('<Double-Button-1>', lambda e: self.edit_segment())

    def browse_input(self):
        """浏览输入视频"""
        filename = filedialog.askopenfilename(
            title="选择视频文件",
            filetypes=[
                ("视频文件", "*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm"),
                ("所有文件", "*.*")
            ]
        )
        if filename:
            self.input_video.set(filename)
            logging.info(f"选择输入视频: {filename}")

    def browse_output(self):
        """浏览输出目录"""
        dirname = filedialog.askdirectory(title="选择输出目录")
        if dirname:
            self.output_dir.set(dirname)
            logging.info(f"选择输出目录: {dirname}")

    def add_segment(self):
        """添加片段"""
        start = self.start_entry.get().strip()
        end = self.end_entry.get().strip()

        if not start or not end:
            messagebox.showwarning("输入错误", "请输入开始时间和结束时间")
            return

        try:
            parse_time(start)
            parse_time(end)
        except (ValueError, AttributeError) as e:
            messagebox.showwarning("格式错误", f"时间格式错误: {e}")
            return

        if start >= end:
            messagebox.showwarning("输入错误", "开始时间必须小于结束时间")
            return

        label = f"片段 {len(self.segments) + 1}: {start} → {end}"
        self.segments.append((start, end, label))
        self.segment_listbox.insert(END, label)
        self.start_entry.delete(0, END)
        self.end_entry.delete(0, END)
        self.start_entry.focus()
        logging.info(f"添加片段: {start} -> {end}")

    def add_multiple_segments(self):
        """添加多个片段的对话框"""
        dialog = Toplevel(self.root)
        dialog.title("添加多个片段")
        dialog.geometry("500x400")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="每行一个片段，格式: 开始时间-结束时间\n例如: 0:00-0:30").pack(pady=10)

        text_frame = ttk.Frame(dialog)
        text_frame.pack(fill='both', expand=True, padx=10, pady=5)

        scrollbar = Scrollbar(text_frame)
        scrollbar.pack(side='right', fill='y')

        text_widget = Text(text_frame, yscrollcommand=scrollbar.set)
        text_widget.pack(side='left', fill='both', expand=True)
        scrollbar.config(command=text_widget.yview)

        def confirm():
            lines = text_widget.get("1.0", END).strip().split('\n')
            count = 0
            for line in lines:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '-' in line:
                    parts = line.split('-')
                    if len(parts) == 2:
                        start, end = parts[0].strip(), parts[1].strip()
                        try:
                            parse_time(start)
                            parse_time(end)
                            if start < end:
                                label = f"片段 {len(self.segments) + 1}: {start} → {end}"
                                self.segments.append((start, end, label))
                                self.segment_listbox.insert(END, label)
                                count += 1
                        except:
                            pass
            dialog.destroy()
            if count > 0:
                messagebox.showinfo("完成", f"成功添加 {count} 个片段")
                logging.info(f"批量添加 {count} 个片段")

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="确认添加", command=confirm).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side='left', padx=5)

    def edit_segment(self):
        """编辑选中的片段"""
        selection = self.segment_listbox.curselection()
        if not selection:
            return

        idx = selection[0]
        start, end, _ = self.segments[idx]

        dialog = Toplevel(self.root)
        dialog.title("编辑片段")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="开始时间:").grid(row=0, column=0, padx=10, pady=10)
        start_var = StringVar(value=start)
        ttk.Entry(dialog, textvariable=start_var, width=15).grid(row=0, column=1, padx=10, pady=10)

        ttk.Label(dialog, text="结束时间:").grid(row=1, column=0, padx=10, pady=10)
        end_var = StringVar(value=end)
        ttk.Entry(dialog, textvariable=end_var, width=15).grid(row=1, column=1, padx=10, pady=10)

        def save():
            try:
                new_start = parse_time(start_var.get())
                new_end = parse_time(end_var.get())
                if start_var.get() >= end_var.get():
                    messagebox.showwarning("错误", "开始时间必须小于结束时间", parent=dialog)
                    return
                self.segments[idx] = (start_var.get(), end_var.get(), f"片段 {idx + 1}: {start_var.get()} → {end_var.get()}")
                self.segment_listbox.delete(idx)
                self.segment_listbox.insert(idx, self.segments[idx][2])
                logging.info(f"编辑片段 {idx + 1}: {start_var.get()} -> {end_var.get()}")
                dialog.destroy()
            except (ValueError, AttributeError) as e:
                messagebox.showwarning("格式错误", f"时间格式错误: {e}", parent=dialog)

        btn_frame = ttk.Frame(dialog)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=10)
        ttk.Button(btn_frame, text="保存", command=save).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side='left', padx=5)

    def delete_segment(self):
        """删除选中的片段"""
        selection = self.segment_listbox.curselection()
        if not selection:
            return

        idx = selection[0]
        deleted_segment = self.segments[idx]
        del self.segments[idx]
        self.segment_listbox.delete(idx)
        logging.info(f"删除片段 {idx + 1}: {deleted_segment[0]} -> {deleted_segment[1]}")

        for i in range(len(self.segments)):
            start, end, _ = self.segments[i]
            self.segments[i] = (start, end, f"片段 {i + 1}: {start} → {end}")

        self.segment_listbox.delete(0, END)
        for _, _, label in self.segments:
            self.segment_listbox.insert(END, label)

    def clear_all_segments(self):
        """清空所有片段"""
        if not self.segments:
            return
        if messagebox.askyesno("确认", "确定要清空所有片段吗?"):
            count = len(self.segments)
            self.segments.clear()
            self.segment_listbox.delete(0, END)
            logging.info(f"清空所有片段，共 {count} 个")

    def move_segment(self, direction):
        """移动片段位置"""
        selection = self.segment_listbox.curselection()
        if not selection:
            return

        idx = selection[0]
        new_idx = idx + direction

        if 0 <= new_idx < len(self.segments):
            self.segments[idx], self.segments[new_idx] = self.segments[new_idx], self.segments[idx]
            logging.info(f"移动片段: {idx + 1} -> {new_idx + 1}")

            for i in range(len(self.segments)):
                start, end, _ = self.segments[i]
                self.segments[i] = (start, end, f"片段 {i + 1}: {start} → {end}")

            self.segment_listbox.delete(0, END)
            for _, _, label in self.segments:
                self.segment_listbox.insert(END, label)

            self.segment_listbox.selection_set(new_idx)

    def quick_add_segments(self):
        """快速添加多个片段"""
        text = self.quick_entry.get().strip()
        if not text:
            return

        count = 0
        for part in text.split(','):
            part = part.strip()
            if '-' in part:
                parts = part.split('-')
                if len(parts) == 2:
                    start, end = parts[0].strip(), parts[1].strip()
                    try:
                        parse_time(start)
                        parse_time(end)
                        if start < end:
                            label = f"片段 {len(self.segments) + 1}: {start} → {end}"
                            self.segments.append((start, end, label))
                            self.segment_listbox.insert(END, label)
                            count += 1
                    except:
                        pass

        self.quick_entry.delete(0, END)
        if count > 0:
            self.status_label.config(text=f"已添加 {count} 个片段")
            logging.info(f"快速添加 {count} 个片段")
        else:
            messagebox.showwarning("格式错误", "未识别到有效的片段格式")

    def start_processing(self):
        """开始处理视频"""
        if self.is_processing:
            return

        input_video = self.input_video.get().strip()
        if not input_video:
            messagebox.showwarning("输入错误", "请选择输入视频文件")
            return

        if not os.path.exists(input_video):
            messagebox.showerror("文件不存在", f"视频文件不存在: {input_video}")
            return

        output_dir = self.output_dir.get().strip()
        if not output_dir:
            messagebox.showwarning("输入错误", "请选择输出目录")
            return

        if not self.segments:
            messagebox.showwarning("输入错误", "请添加至少一个片段")
            return

        logging.info(f"开始分割视频: {input_video} -> {output_dir}")
        self.is_processing = True
        self.start_button.config(state='disabled')
        self.progress['value'] = 0
        self.status_label.config(text="正在处理...")

        thread = threading.Thread(target=self.process_videos)
        thread.daemon = True
        thread.start()

    def process_videos(self):
        """后台处理视频"""
        try:
            input_video = self.input_video.get().strip()
            output_dir = self.output_dir.get().strip()
            segments = [(s, e) for s, e, _ in self.segments]

            def progress(current, total):
                self.root.after(0, lambda: self.progress.config(value=(current / total) * 100))
                self.root.after(0, lambda: self.status_label.config(
                    text=f"正在处理片段 {current}/{total}..."
                ))

            results = cut_video_segments(
                input_video,
                output_dir,
                segments,
                progress_callback=progress
            )

            success = sum(1 for _, ok, _ in results if ok)
            failed = len(results) - success

            self.root.after(0, lambda: messagebox.showinfo(
                "处理完成",
                f"处理完成！\n成功: {success} 个\n失败: {failed} 个"
            ))
            self.root.after(0, lambda: self.status_label.config(text="处理完成"))

        except Exception as e:
            logging.error(f"处理失败: {str(e)}", exc_info=True)
            self.root.after(0, lambda: messagebox.showerror("错误", f"处理失败: {str(e)}"))
            self.root.after(0, lambda: self.status_label.config(text="处理失败"))

        finally:
            self.is_processing = False
            self.root.after(0, lambda: self.start_button.config(state='normal'))
            self.root.after(0, lambda: self.progress.config(value=100))

    def open_output_dir(self):
        """打开输出目录"""
        output_dir = self.output_dir.get().strip()
        if output_dir and os.path.exists(output_dir):
            if os.name == 'nt':  # Windows
                os.startfile(output_dir)
            elif os.uname().sysname == 'Darwin':  # macOS
                subprocess.run(['open', output_dir])
            else:  # Linux
                subprocess.run(['xdg-open', output_dir])
        else:
            messagebox.showwarning("目录不存在", "输出目录不存在")


def main():
    try:
        with open(LOG_FILE, 'w', encoding='utf-8') as f:
            f.write('')
    except:
        pass
    
    setup_logging()
    logging.info("程序启动")
    
    root = Tk()
    app = VideoCutterApp(root)
    
    def on_closing():
        logging.info("程序关闭")
        root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
