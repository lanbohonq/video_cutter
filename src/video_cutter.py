import os
import subprocess
from datetime import timedelta

def parse_time(t):
    """
    支持:
    - 秒 (int/float)
    - "HH:MM:SS"
    - "MM:SS"
    """
    if isinstance(t, (int, float)):
        return str(t)

    parts = list(map(float, t.split(":")))
    if len(parts) == 3:
        h, m, s = parts
    elif len(parts) == 2:
        h, m, s = 0, parts[0], parts[1]
    else:
        raise ValueError(f"时间格式错误: {t}")

    total_seconds = int(timedelta(hours=h, minutes=m, seconds=s).total_seconds())
    return str(total_seconds)


def cut_video_segments(input_video, output_dir, segments):
    """
    参数:
    - input_video: 视频路径
    - output_dir: 输出目录
    - segments: [(start, end), ...]
    """

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    base_name = os.path.splitext(os.path.basename(input_video))[0]

    for idx, (start, end) in enumerate(segments, 1):
        start_sec = parse_time(start)
        end_sec = parse_time(end)

        output_file = os.path.join(
            output_dir, f"{base_name}_clip_{idx}.mp4"
        )

        cmd = [
            "ffmpeg",
            "-y",                  # 覆盖输出
            "-ss", start_sec,
            "-to", end_sec,
            "-i", input_video,
            "-c", "copy",
            output_file
        ]

        print(f"处理片段 {idx}: {start} -> {end}")
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    print("全部处理完成！")


if __name__ == "__main__":
    input_video = r"D:\Download\test.mp4"
    output_dir = r"C:\Users\BOBOY\Videos"

    # 多段时间
    segments = [
        ("00:00:10", "00:00:20"),
        ("00:01:00", "00:01:30"),
        (90, 120),  # 支持秒
    ]

    cut_video_segments(input_video, output_dir, segments)