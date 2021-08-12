import os

__version__ = '0.3.0'


ffmpeg = ''
"""The path to the installed FFmpeg binary."""
ffprobe = ''
"""The path to the installed FFprobe binary."""
packager = ''
"""The path to the installed Shaka Packager binary."""

# Get the directory path where this __init__.py file resides.
_dir_path = os.path.abspath(os.path.dirname(__file__))

for _file in os.listdir(_dir_path):
  if _file.startswith('ffmpeg'):
    ffmpeg = os.path.join(_dir_path, _file)
    # Readable and executable by all + full permission to root.
    # This is useful at build time, so to give these permissions
    # for all the binaries before packaging them into wheels.
    # It is also useful at runtime to ensure that the executables
    # we offer can be executed as a subprocess.
    os.chmod(ffmpeg, 0o755)
  elif _file.startswith('ffprobe'):
    ffprobe = os.path.join(_dir_path, _file)
    os.chmod(ffprobe, 0o755)
  elif _file.startswith('packager'):
    packager = os.path.join(_dir_path, _file)
    os.chmod(packager, 0o755)
