import os
import platform

__version__ = '1.2.2'  # x-release-please-version


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
  'aarch64': 'arm64',  # Linux reports this key
  'arm64': 'arm64',  # Mac reports this key
}[platform.machine()]

# Specific versions of Ubuntu with special builds for hardware-encoding.
_ubuntu_versions_with_hw_encoders = (
  '22.04',
  '24.04',
)

# Module level variables.
ffmpeg = os.path.join(_dir_path, 'ffmpeg-{}-{}'.format(_os, _cpu))
"""The path to the installed FFmpeg binary."""

ffprobe = os.path.join(_dir_path, 'ffprobe-{}-{}'.format(_os, _cpu))
"""The path to the installed FFprobe binary."""

packager = os.path.join(_dir_path, 'packager-{}-{}'.format(_os, _cpu))
"""The path to the installed Shaka Packager binary."""

# Special overrides for Ubuntu builds with hardware encoding support.
# These are not static binaries, and so they must be matched to the distro.
if _os == 'linux':
  import distro

  if distro.id() == 'ubuntu':
    if distro.version() in _ubuntu_versions_with_hw_encoders:
      suffix = '-ubuntu-' + distro.version()
      ffmpeg += suffix
