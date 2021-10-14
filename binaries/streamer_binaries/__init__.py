import os
import platform

__version__ = '0.5.2'


# Get the directory path where this __init__.py file resides.
_dir_path = os.path.abspath(os.path.dirname(__file__))

# Compute the part of the file name that indicates the OS.
_os = {
  'Linux': 'linux',
  'Windows': 'win',
  'Darwin': 'osx',
}[platform.system()]

# Compute the part of the file name that indicates the CPU architecture.
_cpu = {
  'x86_64': 'x64',  # Linux/Mac report this key
  'AMD64': 'x64',  # Windows reports this key
  'aarch64': 'arm64',
}[platform.machine()]

# Module level variables.
ffmpeg = os.path.join(_dir_path, 'ffmpeg-{}-{}'.format(_os, _cpu))
"""The path to the installed FFmpeg binary."""

ffprobe = os.path.join(_dir_path, 'ffprobe-{}-{}'.format(_os, _cpu))
"""The path to the installed FFprobe binary."""

packager = os.path.join(_dir_path, 'packager-{}-{}'.format(_os, _cpu))
"""The path to the installed Shaka Packager binary."""

