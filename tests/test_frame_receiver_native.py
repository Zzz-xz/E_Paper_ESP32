"""直接运行固件使用的收图循环，验证断流和持续零碎数据都不会延长总期限。"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def test_frame_receiver_deadline_and_fragmented_data(tmp_path):
    compiler = shutil.which("g++")
    if not compiler:
        pytest.skip("原生固件收图测试需要 PATH 中的 g++。")
    root = Path(__file__).resolve().parents[1]
    binary = tmp_path / ("frame_receiver.exe" if sys.platform == "win32" else "frame_receiver")
    subprocess.run([compiler, "-std=c++11", "-Wall", "-Wextra", "-Werror", "-I", str(root / "include"),
                    str(root / "tests/native/frame_receiver_test.cpp"), "-o", str(binary)],
                   check=True, capture_output=True, timeout=30)
    subprocess.run([str(binary)], check=True, capture_output=True, timeout=5)
