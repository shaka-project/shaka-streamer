import os

__version__ = '0.5.0'


# Module level variables.
ffmpeg = ''
"""The path to the installed FFmpeg binary."""
ffprobe = ''
"""The path to the installed FFprobe binary."""
packager = ''
"""The path to the installed Shaka Packager binary."""


# Get the directory path where this __init__.py file resides.
_dir_path = os.path.abspath(os.path.dirname(__file__))

# This will be executed at import time.
for _file in os.listdir(_dir_path):
  if _file.startswith('ffmpeg'):
    ffmpeg = os.path.join(_dir_path, _file)
  elif _file.startswith('ffprobe'):
    ffprobe = os.path.join(_dir_path, _file)
  elif _file.startswith('packager'):
    packager = os.path.join(_dir_path, _file)
