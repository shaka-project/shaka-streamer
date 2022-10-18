from pathlib import Path

import pytest

from streamer import controller_node

MODULE = "streamer.controller_node"


@pytest.fixture
def input_config_dict(tmpdir):
    input_file = Path(tmpdir / "input.mp4")
    input_file.touch()
    return {
        "inputs": [
            {
                "name": str(input_file),
                "media_type": "video",
            }
        ]
    }


@pytest.fixture
def pipeline_config_dict():
    return {
        "streaming_mode": "vod",
        "resolutions": ["480p", "360p"],
        "channel_layouts": ["stereo"],
        "audio_codecs": ["aac"],
        "video_codecs": ["h264"],
        "manifest_format": ["hls"],
        "segment_size": 10,
        "segment_per_file": True,
    }


class TestControllerNode:
    @pytest.fixture(autouse=True)
    def mock_subprocess_execution_components(self, mocker):
        # Since currently the tests in this class only test validation logic,
        # we mock out the parts which cause subprocess execution as
        # they're not important.
        mocker.patch(f"{MODULE}.InputConfig")
        mocker.patch(f"{MODULE}.CloudNode")

    def test_start_raises_if_bucket_url_and_google_cloud_sdk_not_found(self, tmpdir):
        node = controller_node.ControllerNode()

        with pytest.raises(controller_node.VersionError):
            node.start(
                output_location=str(tmpdir),
                input_config_dict={},
                pipeline_config_dict={},
                bitrate_config_dict={},
                bucket_url="gs://my_gcs_bucket/folder/",
                check_deps=True,
                use_hermetic=False,
            )

    def test_start_not_raises_if_s3_bucket_url_and_google_cloud_sdk_not_found(
        self, tmpdir, input_config_dict, pipeline_config_dict
    ):
        node = controller_node.ControllerNode()

        node.start(
            output_location=str(tmpdir),
            input_config_dict=input_config_dict,
            pipeline_config_dict=pipeline_config_dict,
            bitrate_config_dict={},
            bucket_url="s3://my_gcs_bucket/folder/",
            check_deps=True,
            use_hermetic=False,
        )
