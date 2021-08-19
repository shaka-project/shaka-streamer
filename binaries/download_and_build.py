import sys

# This import will download the binaries we need.
# This import is blocking until all the binaries have been downloaded.
import download_binaries

# set the sys.argv[1] to the path of the yaml output file.
# The build script will use it to build the wheels.
sys.argv = [
    '',
    download_binaries.YAML_OUTPUT_FILE,
  ]

# This import will build the binaries as python wheels
# for each platform we support.
import build