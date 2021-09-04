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


def _change_permissions_if_needed(file):
  """This function will try to change the bundled executables permssions
  as needed.  This is useful at build time, so to give the needed permissions
  to all the binaries before packaging them into wheels.  It is also useful
  at runtime to ensure that the executables we offer can be executed
  as a subprocess.
  """

  executable_by_owner = 0o100
  perms = os.stat(file).st_mode
  # If it already has executable permssions, we don't chmod.
  # As chmod may require root permssions.
  if (perms | executable_by_owner) == perms:
    return
  # Else we will change the permissions to 0o755.
  # Readable and executable by all + full permissions to owner.
  default_permissions = 0o755 # rwxr-xr-x
  # This might raise PermissionError.
  os.chmod(file, default_permissions)


# This will be executed at import time.
for _file in os.listdir(_dir_path):
  if _file.startswith('ffmpeg'):
    ffmpeg = os.path.join(_dir_path, _file)
    _change_permissions_if_needed(ffmpeg)
  elif _file.startswith('ffprobe'):
    ffprobe = os.path.join(_dir_path, _file)
    _change_permissions_if_needed(ffprobe)
  elif _file.startswith('packager'):
    packager = os.path.join(_dir_path, _file)
    _change_permissions_if_needed(packager)
