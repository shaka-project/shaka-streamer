import sys

# This import will download the binaries we need.
# This import is blocking until all the binaries have been downloaded.
import download_binaries

# Set the sys.argv[1] to the path of the yaml output file that
# the build script will use to build the wheels.
sys.argv = [
    '',
    download_binaries.YAML_OUTPUT_FILE,
  ]

# This import will build the wheels for each platform we support.
import build