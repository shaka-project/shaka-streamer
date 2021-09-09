# Copyright 2021 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Contains the helper classes for HLS parsing and concatenation."""

import os
import re
import math
import posixpath
from typing import List, Dict, Set, Optional, Tuple
from streamer.output_stream import AudioOutputStream, OutputStream, TextOutputStream, VideoOutputStream
from streamer.bitrate_configuration import VideoCodec, AudioCodec, VideoResolution, AudioChannelLayout
from streamer.packager_node import PackagerNode


class MediaPlaylist:
  """A class representing a media playlist(any playlist that references
  media files or media files' segments whether they were video/audio/text files).
  
  The information collected from the master playlist about
  a specific media playlist such as the bitrate, codec, etc...
  is also stored here in `self.stream_info` dictionary.
  
  Keep in mind that a stream variant playlist is also a MediaPlaylist.
  """
  
  current_stream_index = 0
  """A number that is shared between all the MediaPlaylist objects to be used
  to generate unique file names in the format 'stream_<current_stream_index>.m3u8'
  """
  
  HEADER_TAGS = ('#EXTM3U', '#EXT-X-VERSION', '#EXT-X-PLAYLIST-TYPE')
  """Common header tags to search for so we don't store them
  in `MediaPlaylist.content`.  These tags must be defined only one time
  in a playlist, and written at the top of a media playlist file once.
  """
  
  def __init__(self,
               stream_info: Dict[str, str],
               dir_name: Optional[str] = None,
               output_dir: Optional[str] = None,
               streams_map: Optional[Dict[str, OutputStream]] = None):
    """Given a `stream_info` and the `dir_name`, this method finds the media
    playlist file, parses it, and stores relevant parts of the playlist in
    `self.content`.
    
    It also updates the segment paths to make it relative to `output_dir`
    
    A `streams_map` is used to match this media playlist to its OutputStream
    object.
    """
    
    self.stream_info = stream_info
    self.duration = 0.0
    self.target_duration = 0
    
    self.content = ''
    
    if dir_name is None:
      # Do not read, The content will be added manually.
      return
    
    # If there is a file to read, we MUST have a streams_map to match this
    # media playlist file with its OutputStream.
    assert streams_map is not None
    
    period_dir = os.path.relpath(dir_name, output_dir)
    media_playlist_file = os.path.join(dir_name,
                                       _unquote(self.stream_info['URI']))
    
    with open(media_playlist_file) as media_playlist:
      line = media_playlist.readline()
      while line:
        if line.startswith('#EXTINF'):
          # Add this segment duration to the total duration.
          # This will be used to re-calculate the average bitrate.
          self.duration += float(line[len('#EXTINF:'):].split(',', 1)[0])
          self.content += line
          line = media_playlist.readline()
          # If a byterange exists, add it to the content.
          if line.startswith('#EXT-X-BYTERANGE'):
            self.content += line
            line = media_playlist.readline()
          # Update the segment's URI.
          self.content += posixpath.join(period_dir ,line)
        elif line.startswith('#EXT-X-MAP'):
          # An EXT-X-MAP must have a URI attribute and optionally
          # a BYTERANGE attribute.
          attribs = _extract_attributes(line)
          self.content += '#EXT-X-MAP:URI=' + _quote(
              posixpath.join(period_dir, _unquote(attribs['URI'])))
          if attribs.get('BYTERANGE'):
            self.content += ',BYTERANGE=' + attribs['BYTERANGE']
          self.content += '\n'
        elif line.startswith(MediaPlaylist.HEADER_TAGS + ('#EXT-X-ENDLIST',)):
          # Skip header and end-list tags.
          pass
        elif not line.startswith('#EXT'):
          # Skip comments.
          pass
        elif line.startswith('#EXT-X-TARGETDURATION'):
          self.target_duration = int(line[len('#EXT-X-TARGETDURATION:'):])
        else:
          # Store lines that didn't match one of the above cases.
          # Like ENCRYPTIONKEYS, DISCONTINUITIES, COMMENTS, etc... .
          self.content += line
        line = media_playlist.readline()
    
    # Set the features we need to access easily while performing the concatenation.
    # Features like codec, channel_layout, resolution, etc... .
    self._set_features(streams_map)
  
  def _set_features(self, streams_map: Dict[str, OutputStream]) -> None:
    """Get the audio and video codecs and other relevant stream features
    from the matching OutputStream in the `streams_map`, this will be used
    in the codec matching process in the concat_xxx() methods, but the codecs
    that will be written in the final concatenated master playlist will be
    the codecs from stream_info dictionary(in HLS syntax).
    """
    
    # We can't depend on the stream_info['CODECS'] to get the codecs from because
    # this is only present for STREAM-INF, this makes it harder to get codecs for
    # audio segments. Also if we try to get the audio codecs from one of the 
    # #EXT-X-STREAM-INF tags we will have to match these codecs with each stream,
    # for example, a codec attribute might be CODECS="avc1,ac-3,mp4a,opus",
    # the video codec is put first then the audio codecs are put in 
    # lexicographical order(by observation), which isn't necessary the same order of 
    # #EXT-X-MEDIA in the master playlist, thus there is no solid baseground for 
    # matching the codecs using the information in the master playlist.
    
    output_stream: Optional[OutputStream] = None
    lines = self.content.split('\n')
    # We need to seek to the first line with the tag #EXTINF.  The line after
    # will have the URI we need, but if we encounter a byterange tag we need to
    # advance one more line.
    for i in range(len(lines)):
      # Don't use the URIs from any tag to try to extract codec information.
      # We should not rely on the exact structure of file names for this.
      # Use stream_maps instead.
      line = lines[i]
      if line.startswith('#EXTINF'):
        line = lines[i + 1]
        if line.startswith('#EXT-X-BYTERANGE'):
          line = lines[i + 2]
        file_name = os.path.basename(line)
        # Index the file_name and don't use dict.get() .
        # There MUST be a match.
        output_stream = streams_map[file_name]
        break
    
    assert output_stream, 'No media file found in this media playlist'
    self.codec = output_stream.codec
    if isinstance(output_stream, VideoOutputStream):
      self.resolution = output_stream.resolution
    elif isinstance(output_stream, AudioOutputStream):
      self.channel_layout = output_stream.layout
      # We will get the language from the stream_info because the stream information
      # is provided by Packager.  We might have mixed 3-letter and 2-letter format
      # from the Streamer, but Packager reduces them all to 2-letter language tag.
      self.language = _unquote(self.stream_info.get('LANGUAGE', '"und"'))
    elif isinstance(output_stream, TextOutputStream):
      self.language = _unquote(self.stream_info.get('LANGUAGE', '"und"'))
  
  def write(self, dir_name: str, media_playlist_header: str):
    """Writes a media playlist whose file name is `self.stream_info['URI']`
    in the directory `dir_name`.
    """
    
    file_path = os.path.join(dir_name, _unquote(self.stream_info['URI']))
    with open(file_path, 'w') as media_playlist_file:
      content = media_playlist_header
      content += '#EXT-X-TARGETDURATION:' + str(self.target_duration) + '\n\n'
      content += self.content
      content += '#EXT-X-ENDLIST\n'
      media_playlist_file.write(content)
  
  @staticmethod
  def extract_header(file_path: str) -> str:
    """Extracts the common media playlist header(parts we can't store
    in `self.content`).  We then write this header once at the top of
    the file when MediaPlaylist.write() is called.
    """
    
    header = ''
    with open(file_path, 'r') as media_playlist:
      line = media_playlist.readline()
      while line:
        # Capture the M3U tag, PlaylistType, and ExtVersion.
        if line.startswith(MediaPlaylist.HEADER_TAGS):
          header += line
        line = media_playlist.readline()
    return header
  
  @staticmethod
  def _similar_stream_info(media_playlists: List['MediaPlaylist']
                                ) -> Dict[str, str]:
    """A helper method, used to return the stream_info values that are
    identical across all the streams.
    
    A non-empty list must be passed for the parameter `media_playlists`.
    """
    
    assert len(media_playlists), ('There MUST be at least one media playlist'
                                  'to collect its stream information')
    # Get an arbitrary stream info.
    stream_info = media_playlists[0].stream_info.copy()
    
    for key in list(stream_info):
      for media_playlist in media_playlists:
        # If a media playlist has a different value for this key, pop it.
        if media_playlist.stream_info.get(key) != stream_info[key]:
          stream_info.pop(key)
          break
    
    return stream_info
  
  @staticmethod
  def _get_bandwidth(var_playlists: List['MediaPlaylist'],
                     durations: List[float]) -> Dict[str, str]:
    """A helper method to get the peak and average bandwidth
    for stream variants.
    
    For the BANDWIDTH we pick the maximum one we have.
    BANDWIDTH = max((BANDWIDTH)s)
    
    For the AVERAGE-BANDWIDTH we perform a weighted average by duration.
    AVERAGE-BANDWIDTH = (AVERAGE-BANDWIDTH)s . (DURATION)s
                        /sum((DURATION)s)
    """
    
    band, avg_band = 0, 0.0
    for var_playlist, duration in zip(var_playlists, durations):
      band = max(int(var_playlist.stream_info['BANDWIDTH']), band)
      avg_band += int(var_playlist.stream_info['AVERAGE-BANDWIDTH']) * duration
    
    return {
        'BANDWIDTH': str(band),
        'AVERAGE-BANDWIDTH': str(math.ceil(avg_band/sum(durations)))
      }
  
  @staticmethod
  def _get_hls_codec(var_playlists: List['MediaPlaylist']) -> str:
    """A helper method to get all the possible codecs for a concatenated stream
    variant, which is all the codecs present in all the variants(in different
    periods) that will be concatenated.
    """
    
    codec_strings: Set[str] = set()
    for var_playlist in var_playlists:
      codec_strings.update(_unquote(
          var_playlist.stream_info['CODECS']).split(','))
    
    return _quote(','.join(codec_string for
                           codec_string in codec_strings))
  
  @staticmethod
  def _next_unique_name() -> Dict[str, str]:
    """Returns a unique NAME and URI."""
    
    stream_name = 'stream_' + str(MediaPlaylist.current_stream_index)
    MediaPlaylist.current_stream_index += 1
    
    return {
        'NAME': _quote(stream_name),
        'URI': _quote(stream_name + '.m3u8')
      }
  
  @staticmethod
  def _max_channels(aud_playlists: List['MediaPlaylist']
                    ) -> Dict[str, str]:
    """Returns the maximum channel count in the given audio playlists."""
    
    return {
        'CHANNELS': _quote(str(max(
            aud_playlist.channel_layout.max_channels for
            aud_playlist in aud_playlists
      )))}
  
  @staticmethod
  def _max_target_dur(media_playlists: List['MediaPlaylist']) -> int:
    """Returns the maximum target duration in the given media playlists."""
    
    return max(media_playlist.target_duration for
               media_playlist in media_playlists)
  
  @staticmethod
  def _fit_missing_lang(variant_options: List['MediaPlaylist'],
                        language: str) -> str:
    """Returns a substitution language for a missing language by considering
    the languages of the given variants.
    
    `variant_options` are audio or text playlists for the same input that
    we can choose a language from.
    
    `language` is the language this method will try to find a best fit for.
    """
    
    # Set the best_fit to be an arbitrary language for now.
    best_fit = variant_options[0].language
    language_base = language.split('-', 1)[0]
    
    for variant in variant_options:
      best_fit_base = best_fit.split('-', 1)[0]
      candidate = variant.language
      candidate_split = candidate.split('-', 1)
      candidate_base = candidate_split[0]
      candidate_is_regional = len(candidate_split) > 1
      # Only kick the previous best fit out when: The base of the candidate 
      # is the same as the base of the original language AND (the base of 
      # the best fit is not the same as the base of the original language
      # OR the candidate is a regional variant).
      if language_base == candidate_base:
        if language_base != best_fit_base or candidate_is_regional:
          best_fit = candidate
      # Note that no perfect match would ever occur, as this method 
      # is called only when a perfect match is missing.
    
    return best_fit
  
  @staticmethod
  def concat_sub(all_txt_playlists: List[List['MediaPlaylist']],
                 durations: List[float]) -> List['MediaPlaylist']:
    """A method that concatenates subtitle streams based on the language of the subtitles
    for each period, it will concatenate all the english subtitles, french subtitles, etc...
    and put them ordered in periods where a discontinuity is inserted between them.
    
    A `x=List['MediaPlaylists']` is returned, where `len(x)` is the total 
    number of langauges found, and the number of periods(discontinuities) in each playlist
    is `len(all_txt_playlists)`.
    
    When no subtitles are found for a specific langauge for a specific period, we
    try to substitute for it with another language, when no substitution is possible, 
    we insert an empty WEBVTT content as a filler for this period's duration.
    
    All the language un-annotated streams for each period gets concatenated together.
    """
    
    def non_nones(items: List[Optional[MediaPlaylist]]) -> List[MediaPlaylist]:
      """Return the elements of the list which are not None."""
      
      return [item for item in items if item is not None]
    
    # Extract all the languages from every stream.
    langs: Set[str] = set()
    for txt_playlists in all_txt_playlists:
      for txt_playlist in txt_playlists:
        langs.add(txt_playlist.language)
    
    # Create and initialize a division map to divide streams of different
    # languages into.
    division: Dict[str, List[Optional[MediaPlaylist]]] = {}
    for lang in langs:
      division[lang] = []
      # Assume all media playlists for lang are not there at the begining.
      for _ in range(len(all_txt_playlists)):
        # None = no media playlist with this language for this period.
        division[lang].append(None)
    
    # Add the ith media playlist in the ith position for its language division.
    for i, txt_playlists in enumerate(all_txt_playlists):
      for txt_playlist in txt_playlists:
        # Assume that for any langauge, there is at most one stream for it.
        # NOTE: A duplicate second language will overwrite the first one.
        division[txt_playlist.language][i] = txt_playlist
    
    # Try to substitute for missing languages if possible.
    for i in range(len(all_txt_playlists)):
      # All the language options that we can use to substitute for a missing
      # language in this period.
      txt_playlist_options = non_nones([division[lg][i] for lg in langs])
      # We can query `_fit_missing_lang()` only if we have some text
      # streams available, otherwise, we leave them Nones as they are.
      if len(txt_playlist_options):
        for lang in langs:
          if not division[lang][i]:
              sub_lang = MediaPlaylist._fit_missing_lang(txt_playlist_options,
                                                         lang)
              division[lang][i] = division[sub_lang][i]
    
    concat_txt_playlists: List[MediaPlaylist] = []
    for lang, optional_txt_playlists in division.items():
      stream_info = MediaPlaylist._similar_stream_info(
          # There must be at least one that isn't None.
          non_nones(optional_txt_playlists))
      if lang != 'und':
        # Put the language attribute in case it was removed.
        stream_info['LANGUAGE'] = _quote(lang)
      # Get a unique NAME and URI.
      stream_info.update(MediaPlaylist._next_unique_name())
      concat_txt_playlist = MediaPlaylist(stream_info)
      # Set the target duration of the concat playlist to the max of 
      # all children playlists.
      concat_txt_playlist.target_duration = MediaPlaylist._max_target_dur(
          non_nones(optional_txt_playlists))
      for i, optional_txt_playlist in enumerate(optional_txt_playlists):
        if optional_txt_playlist:
          # If a playlist is there, append it.
          concat_txt_playlist.content += optional_txt_playlist.content
        else:
          # If no playlist were found for this period, we create a time gap
          # by filling the period's duration with an empty string.
          ext_inf_count = math.ceil(durations[i] /
                                    concat_txt_playlist.target_duration)
          for _ in range(ext_inf_count):
            concat_txt_playlist.content += (
                '#EXTINF:' + str(durations[i] / ext_inf_count) + ',\n' +
                'data:text/vtt;charset=utf-8,WEBVTT%0A%0A\n')
        # Add a discontinuity after each period.
        concat_txt_playlist.content += '#EXT-X-DISCONTINUITY\n\n'
      concat_txt_playlists.append(concat_txt_playlist)
    
    return concat_txt_playlists
  
  @staticmethod
  def concat_aud_common(all_aud_playlists: List[List['MediaPlaylist']]
                        ) -> Dict[AudioCodec,
                                  Dict[str,
                                       Dict[AudioChannelLayout,
                                            List['MediaPlaylist']]]]:
    """A common method that is used to divide the audio playlists into a structure
    that is easy to process.
    
    This common method is used by `concat_aud` and `concat_aud_only` methods.
    """
    
    # Extract all the codecs, languages, and channel layouts.
    codecs: Set[AudioCodec] = set()
    langs: Set[str] = set()
    channels: Set[AudioChannelLayout] = set()
    for aud_playlists in all_aud_playlists:
      for aud_playlist in aud_playlists:
        assert isinstance(aud_playlist.codec, AudioCodec)
        codecs.add(aud_playlist.codec)
        langs.add(aud_playlist.language)
        channels.add(aud_playlist.channel_layout)
    
    # Create and initialize a division map.
    division: Dict[AudioCodec,
                   Dict[str,
                        Dict[AudioChannelLayout,
                             List['MediaPlaylist']]]] = {}
    
    for codec in codecs:
      division[codec] = {}
      for lang in langs:
        division[codec][lang] = {}
        for channel in channels:
          division[codec][lang][channel] = []
    
    # This logic inside here is done on period basis.
    for aud_playlists in all_aud_playlists:
      # Initialize a mapping between audio codecs and language to a list of
      # media playlists with channel layouts available.
      codec_lang_division: Dict[AudioCodec, Dict[str, List[MediaPlaylist]]] = {}
      for codec in codecs:
        codec_lang_division[codec] = {}
        for lang in langs:
          codec_lang_division[codec][lang] = []
      # For every audio playlist in this period, append it to the matching 
      # codec/language.
      for aud_playlist in aud_playlists:
        assert isinstance(aud_playlist.codec, AudioCodec)
        codec_lang_division[aud_playlist.codec][aud_playlist.language].append(
            aud_playlist)
      # Sort and replace the missing languages in the codec_lang_division map.
      for codec in codecs:
        for lang in langs:
          # If this language for this codec in this period has no media playlists
          # for any channel layout, this means that the language itself
          # is missing.  We will try to find a substitution for it.
          if not len(codec_lang_division[codec][lang]):
            aud_playlist_options = [codec_lang_division[codec][lang][0] for
                                    lang in langs
                                    if len(codec_lang_division[codec][lang])]
            sub_lang = MediaPlaylist._fit_missing_lang(aud_playlist_options,
                                                       lang)
            # Replace the empty codec_lang_division[codec][lang] with the
            # substitution language with the same codec.
            codec_lang_division[codec][lang] = codec_lang_division[codec][sub_lang]
          # Sort the media playlists ascendingly based on the channel layouts.
          codec_lang_division[codec][lang].sort(key=lambda pl: pl.channel_layout)
          # Fill the division map for the current period from the codec_lang_division map.
          for i, channel in enumerate(sorted(channels)):
            division[codec][lang][channel].append(
                # We will try to append the ith audio playlist which has
                # channel layout of `channel`(the for loop variable), but
                # if we don't have the ith audio playlist, we can substitute
                # for it with the max audio playlist in terms of channel layout.
                # This would be an optimal substitution since it is performed only
                # at the higher channel layouts, while the lower channel layouts
                # MUST always align since they had a shared pipeline configuration.
                codec_lang_division[codec][lang][min(
                    i, len(codec_lang_division[codec][lang]) - 1)])
    
    return division
  
  @staticmethod
  def concat_aud(all_aud_playlists: List[List['MediaPlaylist']]
                 ) -> List['MediaPlaylist']:
    """Concatenates multiple audio playlists into one multi-period playlist for
    different languages, codecs, and channel layouts.
    """
    
    division = MediaPlaylist.concat_aud_common(all_aud_playlists)
    
    concat_aud_playlists: List[MediaPlaylist] = []
    for codec, lang_channel_div in division.items():
      for lang, channel_div in lang_channel_div.items():
        for channel, aud_playlists in channel_div.items():
          stream_info = MediaPlaylist._similar_stream_info(
              aud_playlists)
          if lang != 'und':
            # Put the language attribute in case it was removed.
            stream_info['LANGUAGE'] = _quote(lang)
          # Get a unique file name.
          stream_info.update(MediaPlaylist._next_unique_name())
          # Set the max channels for this playlist.
          stream_info.update(MediaPlaylist._max_channels(aud_playlists))
          concat_aud_playlist = MediaPlaylist(stream_info)
          # Set the target duration.
          concat_aud_playlist.target_duration = MediaPlaylist._max_target_dur(
              aud_playlists)
          for aud_playlist in aud_playlists:
            concat_aud_playlist.content += aud_playlist.content
            # Add a discontinuity after each period.
            concat_aud_playlist.content += '#EXT-X-DISCONTINUITY\n\n'
          concat_aud_playlists.append(concat_aud_playlist)
    
    return concat_aud_playlists
  
  @staticmethod
  def concat_aud_only(all_aud_playlists: List[List['MediaPlaylist']],
                      all_var_playlists: List[List['MediaPlaylist']],
                      durations: List[float]) -> List['MediaPlaylist']:
    """Concatenates audio only periods with other audio only periods."""
    
    # Pair audio streams with their equivalent stream variants
    # to retrieve them back later.
    pair: Dict[MediaPlaylist, MediaPlaylist] = {}
    for aud_playlists, var_playlists in zip(all_aud_playlists,
                                            all_var_playlists):
      for aud_playlist in aud_playlists:
        # Search for the matching stream variant.
        for var_playlist in var_playlists:
          if var_playlist.stream_info['URI'] == aud_playlist.stream_info['URI']:
            pair[aud_playlist] = var_playlist
            break
    
    division = MediaPlaylist.concat_aud_common(all_aud_playlists)
    
    concat_aud_only_playlists: List[MediaPlaylist] = []
    for codec, lang_channel_div in division.items():
      for lang, channel_div in lang_channel_div.items():
        for channel, aud_playlists in channel_div.items():
          # Get the variant playlists paired to the current audio playlists.
          var_playlists = [pair[aud_playlist] for aud_playlist in aud_playlists]
          stream_info = MediaPlaylist._similar_stream_info(
              aud_playlists)
          if lang != 'und':
            # Put the language attribute in case it was removed.
            stream_info['LANGUAGE'] = _quote(lang)
          # Get a unique file name.
          stream_info.update(MediaPlaylist._next_unique_name())
          # Set the max channels for this playlist.
          stream_info.update(MediaPlaylist._max_channels(aud_playlists))
          concat_aud_playlist = MediaPlaylist(stream_info)
          # Get the stream info for the paired variant playlists.
          stream_info = MediaPlaylist._similar_stream_info(var_playlists)
          # The URI for the concatenated variant playlist will be the same as
          # the concatenated audio playlist.
          stream_info['URI'] = concat_aud_playlist.stream_info['URI']
          # Get the peak and average bandwidth across all periods
          # for this codec-language-channel triad.
          stream_info.update(MediaPlaylist._get_bandwidth(var_playlists,
                                                          durations))
          # Get the codecs from the associated stream variant playlists.
          stream_info['CODECS'] = MediaPlaylist._get_hls_codec(var_playlists)
          concat_var_playlist = MediaPlaylist(stream_info)
          # Set the target duration.
          concat_aud_playlist.target_duration = MediaPlaylist._max_target_dur(
              aud_playlists)
          for aud_playlist in aud_playlists:
            concat_aud_playlist.content += aud_playlist.content
            # Add a discontinuity after each period.
            concat_aud_playlist.content += '#EXT-X-DISCONTINUITY\n\n'
          # The audio and the stream variant playlist will be exactly the same.
          concat_var_playlist.target_duration = concat_aud_playlist.target_duration
          concat_var_playlist.content = concat_aud_playlist.content
          concat_aud_only_playlists.extend(
              [concat_aud_playlist, concat_var_playlist])
    
    return concat_aud_only_playlists
  
  @staticmethod
  def concat_vid(all_vid_playlists: List[List['MediaPlaylist']],
                 durations: List[float]) -> List['MediaPlaylist']:
    """Concatenates multiple video playlists into one multi-period playlist
    for many resolutions and codecs, it matches the codecs first, then matches
    the resolutions.
    
    It will pick the closest lower resolution for some period(input) if a high
    enough resolution was not available.
    
    A video playlist is a stream variant playlist based on the Packager's output.
    """
    
    # Get all possible video codecs.  We should not use the all codecs available
    # in the pipeline config, because for some codecs we might have given the
    # Packager the 'dash_only' flag.
    codecs: Set[VideoCodec] = set()
    # Also get all the available resolutions.
    resolutions: Set[VideoResolution] = set()
    for vid_playlists in all_vid_playlists:
      for vid_playlist in vid_playlists:
        assert isinstance(vid_playlist.codec, VideoCodec)
        codecs.add(vid_playlist.codec)
        resolutions.add(vid_playlist.resolution)
    
    # Create and initialize a division map.
    division: Dict[VideoCodec,
                   Dict[VideoResolution,
                        List[MediaPlaylist]]] = {}
    for codec in codecs:
      division[codec] = {}
      for resolution in resolutions:
        division[codec][resolution] = []
    
    # In each period do the following:
    for vid_playlists in all_vid_playlists:
      # Initialize a mapping between video codecs and a list of resolutions available.
      codec_division: Dict[VideoCodec, List[MediaPlaylist]] = {}
      for codec in codecs:
        codec_division[codec] = []
      # For every video playlist in this period, append it to the matching codec.
      for vid_playlist in vid_playlists:
        assert isinstance(vid_playlist.codec, VideoCodec)
        codec_division[vid_playlist.codec].append(vid_playlist)
      for codec in codecs:
        # Sort the variants from low resolution to high resolution.
        codec_division[codec].sort(key=lambda pl: pl.resolution)
        for i, resolution in enumerate(sorted(resolutions)):
          division[codec][resolution].append(
              # Append the ith resolution if found, else, append the max
              # available resolution.  This would be a valid choice of
              # grouping every time because all the inputs will have a common
              # lowest resolution, that's because they share the same pipeline
              # configuration.  At some point, some input(s) won't be able to
              # scale up in terms of the resolution as the rest, that's when we
              # pick the highest resolution available for it/them.
              codec_division[codec][min(i, len(codec_division[codec]) - 1)])
    
    concat_vid_playlists: List[MediaPlaylist] = []
    for codec, resolution_division in division.items():
      for resolution, vid_playlists in resolution_division.items():
        stream_info: Dict[str, str] = MediaPlaylist._similar_stream_info(
        vid_playlists)
        # Get a unique URI.
        stream_info.update(MediaPlaylist._next_unique_name())
        # NOTE: stream variants don't have a NAME attribute.
        stream_info.pop('NAME')
        # Get the peak and average bandwidth for this codec-resolution pair.
        stream_info.update(MediaPlaylist._get_bandwidth(vid_playlists,
                                                        durations))
        # Get all the codecs that will be inside the new variant stream playlist.
        stream_info['CODECS'] = MediaPlaylist._get_hls_codec(vid_playlists)
        concat_vid_playlist = MediaPlaylist(stream_info)
        concat_vid_playlist.target_duration = MediaPlaylist._max_target_dur(
            vid_playlists)
        for vid_playlist in vid_playlists:
          concat_vid_playlist.content += vid_playlist.content
          # Add a discontinuity after each period.
          concat_vid_playlist.content += '#EXT-X-DISCONTINUITY\n\n'
        concat_vid_playlists.append(concat_vid_playlist)
    
    return concat_vid_playlists


class MasterPlaylist:
  """A class representing a master playlist."""
  
  def __init__(self,
               file_name: Optional[str] = None,
               output_dir: Optional[str] = None,
               packager: Optional[PackagerNode] = None):
    """Given the path to the master playlist file, this method will read that file
    and search for MediaPlaylists inside it, and instantiate a MediaPlaylist object
    for each one found.
    
    The (MediaPlaylist)'s __init__ method will parse each media playlist and change the
    path of media segments to be relative to `output_dir`.
    
    if `file_name` is None, an empty MasterPlaylist object is returned.
    """
    
    self.playlists: List[MediaPlaylist] = []
    self.duration = 0.0
    
    if file_name is None:
      # Do not read. The media playlists will be appended manually.
      return

    # If there is a file to read, we MUST have a bound packager node
    # to match its streams with each media playlist.
    assert packager is not None
    
    # We will fill this map, file names to (OutputStream)s and will give it out
    # to each media playlist we initialize.  Each media playlist then will pick
    # the right output stream for itself.
    streams_map: Dict[str, OutputStream] = {}
    
    # Add a mapping between single segment file names and their output stream.
    streams_map.update({
        outstream.get_single_seg_file().write_end(): outstream
        for outstream in packager.output_streams
      })
    # Add another mapping between the first segment in multi-segment file names
    # and their corresponding output streams.
    streams_map.update({
        outstream.get_media_seg_file()
        .write_end()
        .replace('$Number$', '1'): outstream
        for outstream in packager.output_streams
      })
    
    dir_name = os.path.dirname(file_name)
    
    with open(file_name, 'r') as master_playlist:
      line = master_playlist.readline()
      while line:
        if line.startswith('#EXT-X-MEDIA'):
          stream_info = _extract_attributes(line)
          self.playlists.append(MediaPlaylist(stream_info, dir_name,
                                              output_dir,
                                              streams_map))
        elif line.startswith('#EXT-X-STREAM-INF'):
          stream_info = _extract_attributes(line)
          # Quote the URI to keep consistent,
          # as the URIs in EXT-X-MEDIA are quoted too.
          stream_info['URI'] = _quote(master_playlist.readline().strip())
          self.playlists.append(MediaPlaylist(stream_info, dir_name,
                                              output_dir,
                                              streams_map))
        line = master_playlist.readline()
      # Get the master playlist duration from an arbitrary stream.
      self.duration = self.playlists[-1].duration
  
  def write(self, file: str,
            master_playlist_header: str,
            media_playlist_header: str,
            comment: str) -> None:
    """Writes the master playlist and the nested media playlists in
    the file system.
    """
    
    dir_name = os.path.dirname(file)
    with open(file, 'w') as master_playlist:
      content = master_playlist_header
      content += comment
      # Write #EXT-X-MEDIA media playlists first.
      for media_playlist in self.playlists:
        if media_playlist.stream_info.get('TYPE'):
          media_playlist.write(dir_name, media_playlist_header)
          content += '#EXT-X-MEDIA:' + ','.join(sorted(
              [key + '=' + value for
               key, value in media_playlist.stream_info.items()])) + '\n'
      content += '\n'
      # Then write #EXT-X-STREAM-INF media playlists.
      for media_playlist in self.playlists:
        if media_playlist.stream_info.get('TYPE') is None:
          media_playlist.write(dir_name, media_playlist_header)
          # We don't write the URI in the attributes of a stream
          # variant playlist.  Pop out the URI.
          uri = _unquote(media_playlist.stream_info.pop('URI'))
          content += '#EXT-X-STREAM-INF:' + ','.join(sorted(
              [key + '=' + value for
               key, value in media_playlist.stream_info.items()])) + '\n'
          content += uri + '\n'
      master_playlist.write(content)
  
  @staticmethod
  def extract_headers(file_path: str) -> Tuple[str, str]:
    """Returns the headers for the master and media playlists using the
    master playlist in `file_path` and any media playlist we find inside
    this master playlist.
    """
    
    header = ''
    with open(file_path, 'r') as master_playlist_file:
      line = master_playlist_file.readline()
      # Store each line in header until one of these tags is encountered.
      while line and not line.startswith(('#EXT-X-MEDIA', '#EXT-X-STREAM-INF')):
        # lstrip() will convert empty lines -> '' but will keep non-empty lines unchanged.
        header += line.lstrip()
        line = master_playlist_file.readline()
      else:
        # Use this media playlist to also extract the MediaPlaylist header.
        if line.startswith('#EXT-X-MEDIA'):
          uri = _unquote(_extract_attributes(line)['URI'])
        elif line.startswith('#EXT-X-STREAM-INF'):
          uri = master_playlist_file.readline().strip()
        else:
          raise RuntimeError('No media playlist found in this master playlist')
        master_playlist_dirname = os.path.dirname(file_path)
        media_playlist_path = os.path.join(master_playlist_dirname, uri)
        return header, MediaPlaylist.extract_header(media_playlist_path)
  
  @staticmethod
  def concat_master_playlists(
    master_playlists: List['MasterPlaylist']) -> 'MasterPlaylist':
    
    def var_is_vid(var_playlists: List['MediaPlaylist']) -> bool:
      """This is useful to detect whether the stream variant playlists in some
      master playlist are video playlists or not.  They could be audio playlists
      as #EXT-X-STREAM-INF because there were no video streams associated
      with this input.
      """
      
      # NOTE: Ideally, this check should be performed on all the STREAM-INF playlists
      # for this input, but Shaka-Packager's output guarantees for us that all the
      # STREAM-INFs will be videos or all will be audios in a master playlist.
      assert len(var_playlists), ('There MUST be at least one stream variant'
                                  ' in a master playlist')
      # NOTE: Since we intentionally indexed the list, it must be a non-empty list,
      # i.e. there must be at least one stream variant in each master playlist.
      return isinstance(var_playlists[0].codec, VideoCodec)
    
    # SEMANTICS:
      # xxx_playlist == one MediaPlaylist object.
      # xxx_playlists == multiple MediaPlaylist objects in the same master playlist.
      # all_xxx_playlists == a list of (xxx_playlists).
    all_txt_playlists: List[List['MediaPlaylist']] = []
    all_aud_playlists: List[List['MediaPlaylist']] = []
    all_var_playlists: List[List['MediaPlaylist']] = []
    # The durations will be used to insert a gap in subtitles playlists when
    # there is no applicable media to insert. Will also be used to calculate
    # the average bandwidth.
    durations: List[float] = []
    
    for master_playlist in master_playlists:
      
      txt_playlists: List['MediaPlaylist'] = []
      aud_playlists: List['MediaPlaylist'] = []
      var_playlists: List['MediaPlaylist'] = []
      
      for media_playlist in master_playlist.playlists:
        stream_type = media_playlist.stream_info.get('TYPE', 'STREAM-INF')
        if stream_type == 'SUBTITLES':
          txt_playlists.append(media_playlist)
        elif stream_type == 'AUDIO':
          aud_playlists.append(media_playlist)
        elif stream_type == 'STREAM-INF':
          var_playlists.append(media_playlist)
        else:
          # TODO: We need a case for CLOSED-CAPTIONS(CC).
          raise RuntimeError("TYPE={} is not recognized".format(stream_type))  
      
      all_txt_playlists.append(txt_playlists)
      all_aud_playlists.append(aud_playlists)
      all_var_playlists.append(var_playlists)
      durations.append(master_playlist.duration)
    
    master_hls = MasterPlaylist()
    master_hls.playlists.extend(
        MediaPlaylist.concat_sub(all_txt_playlists, durations))
    
    if all(not var_is_vid(var_pl) for var_pl in all_var_playlists):
      # When the playlist is audio only, each audio is referenced two times,
      # once in an #EXT-X-MEDIA tag and another time in an #EXT-X-STREAM-INF tag.
      # If the user has an audio-only content, the concatenation will go a little
      # bit different to produce the desired output.
      master_hls.playlists.extend(
          MediaPlaylist.concat_aud_only(
            all_aud_playlists,
            all_var_playlists,
            durations))
    else:
      master_hls.playlists.extend(
          MediaPlaylist.concat_aud(all_aud_playlists))
      master_hls.playlists.extend(
          MediaPlaylist.concat_vid(all_var_playlists, durations))
    
    return master_hls


class HLSConcater:
  """A class that serves as an API for the m3u8 concatenation methods."""
  
  def __init__(self,
               sample_master_playlist_path: str,
               output_location: str):
    """Calls MasterPlaylist.extract_headers() and MediaPlaylist.extract_header()
    and store these headers in their classes respectively.
    
    We use the `output_location` to re-evaluate a media segment paths, and also
    write the concatenation result to this `output_location`.
    """
    
    # Extract common master playlist header, this will call
    # MediaPlaylist.extract_header() to extract the common
    # media playlist header as well.
    (self._master_playlist_header,
     self._media_playlist_header) = MasterPlaylist.extract_headers(
          sample_master_playlist_path)
    # Will be used when writing the concatenated playlists.
    self._output_location = output_location
    self._all_master_playlists: List[MasterPlaylist] = []
    
  def add(self, master_playlist_path: str, packager_node: PackagerNode):
    """Adds a master playlist to the HLSConcater object, to be concatented
    in order when HLSConcater.concat() is called.
    """
    
    self._all_master_playlists.append(
        MasterPlaylist(master_playlist_path,
                       self._output_location,
                       packager_node))
  
  def concat_and_write(self, master_playlist_file_name: str, comment: str = ''):
    """Starts concatenating the added master playlists producing one
    final master playlist.
    
    Then, it writes the concatenated playlists in `output_location` parameter
    passed to the constructor.
    """
    
    concated_master_playlist = MasterPlaylist.concat_master_playlists(
        self._all_master_playlists)
    
    if comment:
      comment = '## ' + comment + '\n\n'
    master_playlist_file_name = os.path.join(self._output_location,
                                             master_playlist_file_name)
    concated_master_playlist.write(master_playlist_file_name,
                                   self._master_playlist_header,
                                   self._media_playlist_header,
                                   comment)


def _extract_attributes(line: str) -> Dict[str, str]:
  """Extracts attributes from an m3u8 #EXT-X tag to a python dictionary."""
  
  attributes: Dict[str, str] = {}
  line = line.strip().split(':', 1)[1]
  # For a tighter search, append ',' and search for it in the regex.
  line += ','
  # Search for all KEY=VALUE,
  matches: List[Tuple[str, str]] = re.findall(
      r'([-A-Z]+)=("[^"]*"|[^",]*),', line)
  for key, value in matches:
    attributes[key] = value
  return attributes

def _quote(string: str) -> str:
  """Puts a string in double quotes."""
  
  return '"' + string + '"'

def _unquote(string: str) -> str:
  """Removes the double quotes surrounding a string."""
  
  return string[1:-1]
