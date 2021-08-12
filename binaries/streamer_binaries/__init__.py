import os


__version__ = '0.3.0'


FFMPEG = ''
"""The path to the installed FFmpeg binary."""
FFPROBE = ''
"""The path to the installed FFprobe binary."""
PACKAGER = ''
"""The path to the installed Shaka Packager binary."""

# Get the directory path where this __init__.py file resides.
_dir_path = os.path.abspath(os.path.dirname(__file__))

for _file in os.listdir(_dir_path):
  if _file.startswith('ffmpeg'):
    FFMPEG = os.path.join(_dir_path, _file)
  elif _file.startswith('ffprobe'):
    FFPROBE = os.path.join(_dir_path, _file)
  elif _file.startswith('packager'):
    PACKAGER = os.path.join(_dir_path, _file)

assert FFMPEG and FFPROBE and PACKAGER