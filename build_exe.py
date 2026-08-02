"""
打包脚本 - 将 AI 弹幕助手打包为独立 exe
"""
import subprocess
import sys
import os
from pathlib import Path

def build_exe():
    """打包为 exe"""
    project_dir = Path(__file__).parent
    spec_content = '''
# -*- mode: python ; coding: utf-8 -*-
block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('config.yaml', '.'),
    ],
    hiddenimports=[
        'PyQt5',
        'danmu_skin',
        'emotion_recognizer',
        'style_advisor',
        'danmu_history',
        'stream_processor',
        'danmu_widget',
        'danmu_stats_panel',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='AI弹幕助手',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
'''
    
    spec_path = project_dir / "danmu_assistant.spec"
    with open(spec_path, "w", encoding="utf-8") as f:
        f.write(spec_content)
    
    print("正在打包...")
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--clean", str(spec_path)],
        cwd=str(project_dir),
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print("打包成功！")
        print(f"输出目录: {project_dir / 'dist'}")
    else:
        print("打包失败:")
        print(result.stderr)
    
    # 清理 spec 文件
    spec_path.unlink(missing_ok=True)
    
    return result.returncode == 0


if __name__ == "__main__":
    success = build_exe()
    sys.exit(0 if success else 1)
