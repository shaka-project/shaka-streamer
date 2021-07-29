# Copyright 2019 Google LLC
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
import enum
from typing import List, Optional, Dict, Set, Tuple, cast
from streamer.bitrate_configuration import VideoCodec, AudioCodec, VideoResolution


class MediaPlaylist:
  """A class representing a media playlist. The information collected from the 
  master playlist about a specific media playlist such as the bitrate, codec, etc...
  is also saved here."""
  
  header = ''
  """A common header for all the MediaPlaylist objects."""
  
  output_dir = ''
  """The output directory that is specified in the command line.
  This will be used to evaluate the relative path to each media segment."""
  
  current_stream_index = 0
  """A number that is shared between all the MediaPlaylist objects to be used to generate
  unique file names in the format 'stream_<current_stream_index>.m3u8'"""
  
  HEADER_TAGS = ('#EXTM3U', '#EXT-X-VERSION', '#EXT-X-PLAYLIST-TYPE')
  """Common header tags to search for and store in `MediaPlaylist.header`.
  These tags must be defined only one time in a playlist, so they should
  not be stored in `self.content`."""
  
  def __init__(self, stream_info: Dict[str, str], dir_name: Optional[str] = None):
    """Given a `stream_info` and the `dir_name`, this method parses a 
    media playlist file and stores relevant parts of the playlist in `self.content`.
    
    It also updates the segment paths to make it relative to `MediaPlaylist.output_dir`"""
    
    self.stream_info = stream_info
    self.duration = 0.0
    self.target_duration = 0
    
    self.content = ''
    
    # Either VideoCodec, AudioCodec, or None.
    self.codec: Optional[enum.Enum] = None
    
    if dir_name is None:
      # Do not read, The content will be added manually.
      return
    
    period_dir = os.path.relpath(dir_name, MediaPlaylist.output_dir)
    with open(os.path.join(
      dir_name, _unquote(self.stream_info['URI']))) as media_playlist:
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
          # Update the URI and save it.
          self.content += os.path.join(period_dir ,line)
        elif line.startswith('#EXT-X-MAP'):
          # An EXT-X-MAP must have a URI attribute and optionally a BYTERANGE attribute.
          attribs = _extract_attributes(line)
          self.content += '#EXT-X-MAP:URI=' + _quote(
            os.path.join(period_dir, _unquote(attribs['URI'])))
          if attribs.get('BYTERANGE'):
            self.content += ',BYTERANGE=' + attribs['BYTERANGE']
          self.content += '\n'
        elif line.startswith(MediaPlaylist.HEADER_TAGS + ('#EXT-X-ENDLIST',)):
          # Escape header and end-list tags.
          pass
        elif line.startswith('#EXT-X-TARGETDURATION'):
          self.target_duration = int(line[len('#EXT-X-TARGETDURATION:'):])
        else:
          # Store lines that didn't match one of the above cases.
          # Like ENCRYPTIONKEYS, DISCONTINUITIES, COMMENTS, etc... .
          self.content += line
        line = media_playlist.readline()
    self._set_codec_res_channels()
  
  def write(self, dir_name: str) -> None:
    file_path = os.path.join(dir_name, _unquote(self.stream_info['URI']))
    with open(file_path, 'w') as media_playlist:
      content = MediaPlaylist.header
      content += '#EXT-X-TARGETDURATION:' + str(self.target_duration) + '\n'
      content += self.content
      content += '#EXT-X-ENDLIST\n'
      media_playlist.write(content)
  
  @staticmethod
  def extract_header(file_path: str) -> None:
    MediaPlaylist.header = ''
    with open(file_path, 'r') as media_playlist:
      line = media_playlist.readline()
      while line:
        # Capture the M3U tag, PlaylistType, and ExtVersion.
        if line.startswith(MediaPlaylist.HEADER_TAGS):
          MediaPlaylist.header += line
        line = media_playlist.readline()
  
  def _set_codec_res_channels(self) -> None:
    """Get the audio and video codecs from file names, this will be used for the
    codec matching process in the concater, but the codecs that will be written in
    the final concated files will be the codecs from stream_info dictionary."""
    
    # We can't depend on the stream_info['CODECS'] to get the codecs from because 
    # this is only present for STREAM-INF, this makes it harder to get codecs for
    # audio segments. Also if we try to get the audio codecs from one of the 
    # #EXT-X-STREAM-INF tags we will have to matche these codecs with each stream,
    # for example a codec attribute might be like CODECS="avc1,ac-3,mp4a,opus",
    # the video codec is put first then the audio codecs are put in 
    # lexicographical order(by observation), which isn't nesseccary the same order of 
    # #EXT-X-MEDIA in the master playlist, thus there is no solid baseground for 
    # matching the codecs using the information in the master playlist.
    
    lines = self.content.split('\n')
    for i in range(len(lines)):
      # Don't use #EXT-X-MAP to get the codec, because HLS specs says
      # it is an optional tag.
      line = lines[i]
      if line.startswith('#EXTINF'):
        line = lines[i+1]
        if line.startswith('#EXT-X-BYTERANGE'):
          line = lines[i+2]
        other, codec = _codec_resolution_channels_regex(
          os.path.basename(line))
        if codec in [codec.value for codec in AudioCodec]:
          self.codec = AudioCodec(codec)
          self.channels = int(other)
        if codec in [codec.value for codec in VideoCodec]:
          self.codec = VideoCodec(codec)
          self.resolution = VideoResolution.get_value(other)
        break
  
  @staticmethod
  def inf_is_vid(inf_playlists: List['MediaPlaylist']) -> bool:
    """This is useful to detect whether the stream-inf playlists are video playlists.
    They could be audio playlists as #EXT-X-STREAM-INF because there were no video stream
    associated with this input."""
    
    # NOTE: Ideally, this check should be performed on all the STREAM-INF playlists
    # for this input, but Shaka-Packager's output guarantees for us that all the 
    # STREAM-INFs will be videos or all will be audios in a master playlist.
    if isinstance(inf_playlists[0].codec, VideoCodec):
      return True
    return False
  
  @staticmethod
  def _keep_similar_stream_info(media_playlists: List['MediaPlaylist']
                                ) -> Dict[str, str]:
    """A helper method, used to keep only the similar stream_info values and pop
    out the values that are different between multiple streams.
    
    A non-empty list must be passed for the `media_playlist` argument."""
    
    # Get an arbitrary stream info.
    stream_info = media_playlists[0].stream_info.copy()

    # list(stream_info) returns a list of keys.
    for key in list(stream_info):
      for media_playlist in media_playlists:
        # If a media playlist has a different value for a key,
        # remove that key.
        if media_playlist.stream_info.get(key) != stream_info[key]:
          stream_info.pop(key)
          break
    
    return stream_info

  @staticmethod
  def _get_bandwidth(inf_playlists: List['MediaPlaylist'],
                     durations: List[float]) -> Tuple[str, str]:
    """A helper method to get the bandwidth and average bandwidth for INF-STEAMs.
    BANDWIDTH = max(BANDWIDTHIs)
    AVERAGE-BANDWIDTH = sum(AVERAGE-BANDWIDTHs*DURATIONs)/sum(DURATIONs)"""
    
    band, avgband = 0, 0.0
    for i, inf_playlist in enumerate(inf_playlists):
      band = max(int(inf_playlist.stream_info['BANDWIDTH']), band)
      avgband += int(inf_playlist.stream_info['AVERAGE-BANDWIDTH']) * durations[i]
    
    return str(band), str(math.ceil(avgband/sum(durations)))
  
  @staticmethod
  def _get_codec(inf_playlists: List['MediaPlaylist']) -> str:
    """A helper method get all the possible codecs for a variant, which is 
    all the codecs present in all the periods of that variant."""
    
    codec_strings: Set[str] = set()
    for inf_playlist in inf_playlists:
      codec_strings.update(_unquote(
        inf_playlist.stream_info['CODECS']).split(','))
      
    return _quote(','.join(codec_string 
                           for codec_string in codec_strings))
  
  @staticmethod
  def _next_unq_name() -> Tuple[str, str]:
    """Returns a unique NAME and URI."""
    
    stream_name = 'stream_' + str(MediaPlaylist.current_stream_index)
    MediaPlaylist.current_stream_index += 1
    
    return _quote(stream_name), _quote(stream_name + '.m3u8')
  
  @staticmethod
  def _max_channels(media_playlists: List['MediaPlaylist']
                    ) -> str:
    """Returns the maximum channel count found in one of the given playlists."""
    
    return _quote(str(max(media_playlist.channels
                          for media_playlist in media_playlists)))
  
  @staticmethod
  def _max_targer_dur(media_playlists: List['MediaPlaylist']) -> int:
    
    return max(media_playlist.target_duration
               for media_playlist in media_playlists)
    
  @staticmethod
  def _fit_missing_lang(variants: List['MediaPlaylist'],
                        lang: str) -> str:
    """Returns a substitution language for a missing language by considering the
    languages of the given variants.
    
    Returns the argument lang only if all the variants are None."""
    
    if not variants:
      # This handles the case when all the sibling playlists have
      # no subtitles either.
      return lang
    
    best_fit: str = _unquote(variants[0].stream_info.get('LANGUAGE', '"und"'))
    lang_base = _unquote(lang).split('-', 1)[0]
    
    for variant in variants:
      candidate = _unquote(variant.stream_info.get('LANGUAGE', '"und"'))
      bsft_base = best_fit.split('-', 1)[0]
      cand_splt = candidate.split('-', 1)
      cand_base, cand_is_reg = cand_splt[0], len(cand_splt) > 1
      # Only kick the previous best fit out when: the base of the candidate 
      # is the same as the base of the original language, and (the base of 
      # the best fit is not the same as the base of the origianl language,
      # or the candidate is a regional variant).
      if lang_base == cand_base:
        if lang_base != bsft_base or cand_is_reg:
          best_fit = candidate
      # Note that no perfect match would ever occur, as this function 
      # is called only when a perfect match is missing.
        
    return _quote(best_fit)
  
  @staticmethod
  def concat_sub(all_txt_playlists: List[List['MediaPlaylist']],
                 durations: List[float]) -> List['MediaPlaylist']:
    """A method that concatenates subtitle streams based on the language of the subtitles
    for each period, it will concatenate all the english subtitles, frensh subtitles, etc...
    and put them ordered in periods where a discontinuity is inserted between them.
    
    A `x=List['MediaPlaylists']` is returned, where `len(x)` is the total 
    number of langauges found, and the number of periods (discontinuities) in each playlist
    is `len(all_txt_playlists)`.
    
    When no subtitles are there for a specific langauge for a specific period, we
    try to substitue for it with other languages, when no substitution is possible, 
    we insert some text saying 'no subtitles' as a filler for this period's duration.
    
    All the language un-annotated streams for each period gets concatenated together."""
    
    # Extract all the languages from every stream.
    langs: Set[str] = set()
    for txt_playlists in all_txt_playlists:
      for txt_playlist in txt_playlists:
        langs.add(txt_playlist.stream_info.get('LANGUAGE', '"und"'))
    
    # Create and initialize a division to divide streams of different
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
        division[txt_playlist.stream_info.get('LANGUAGE', '"und"')][i] = txt_playlist
    
    # Try to substitute for missing languages if possible.
    for i in range(len(all_txt_playlists)):
      for lang in langs:
        if not division[lang][i]:
          division[lang][i] = division[MediaPlaylist._fit_missing_lang(
            _non_nones([division[lg][i] for lg in langs]), lang)][i]
    
    concat_txt_playlists: List[MediaPlaylist] = []
    for lang, opt_txt_playlists in division.items():
      stream_info: Dict[str, str] = MediaPlaylist._keep_similar_stream_info(
        _non_nones(opt_txt_playlists))
      # Put the language in case it was removed.
      if lang != '"und"':
        stream_info['LANGUAGE'] = lang
      # Get a unique name and uri.
      stream_info['NAME'], stream_info['URI'] = MediaPlaylist._next_unq_name()
      concat_txt_playlist = MediaPlaylist(stream_info)
      # Set the target duration of the concated playlist to the max of 
      # all children playlists.
      concat_txt_playlist.target_duration = MediaPlaylist._max_targer_dur(
        _non_nones(opt_txt_playlists))
      for i, opt_txt_playlist in enumerate(opt_txt_playlists):
        if opt_txt_playlist:
          # If a playlist is there, append it.
          concat_txt_playlist.content += opt_txt_playlist.content
        else:
          # If the no playlist were found for this period,
          # Create a time gap filled with dummy data for the period's duration.
          dummy = ',\ndata:text/plain,NO {} SUBTITLES\n'.format(lang.upper())
          # Break it into target duration count and remains, because the target
          # duration might be a prime number, this might cause rounding error.
          td_count = durations[i] // concat_txt_playlist.target_duration
          for _ in range(int(td_count)):
            concat_txt_playlist.content += ('#EXTINF:' + str(
              concat_txt_playlist.target_duration) + dummy)
          # Put whats left in an #EXTINF.
          remains = round(durations[i] % concat_txt_playlist.target_duration, 3)
          if remains:
            concat_txt_playlist.content += '#EXTINF:' + str(remains) + dummy
        # Add a discontinuity after each period.
        concat_txt_playlist.content += '#EXT-X-DISCONTINUITY\n'
      concat_txt_playlists.append(concat_txt_playlist)
    
    return concat_txt_playlists
  
  @staticmethod
  def concat_aud_common(all_aud_playlists: List[List['MediaPlaylist']]
                        ) -> Dict[AudioCodec,
                                  Dict[str,
                                       Dict[int,
                                            List['MediaPlaylist']]]]:
    """A common method that is used to divide the audio playlists into a structure
    that is easy to process.
    
    This common method is used by `concat_aud` and `concat_aud_only` methods."""
    
    # Extract all the codecs, languages, and channel counts.
    codecs: Set[AudioCodec] = set()
    langs: Set[str] = set()
    channels: Set[int] = set()
    for aud_playlists in all_aud_playlists:
      for aud_playlist in aud_playlists:
        assert isinstance(aud_playlist.codec, AudioCodec)
        codecs.add(aud_playlist.codec)
        channels.add(aud_playlist.channels)
        langs.add(aud_playlist.stream_info.get('LANGUAGE', '"und"'))
    
    # Create and initialize a division map.
    division: Dict[AudioCodec,
                   Dict[str,
                        Dict[int,
                             List[Optional['MediaPlaylist']]]]] = {}
    for codec in codecs:
      division[codec] = {}
      for lang in langs:
        division[codec][lang] = {}
        for channel in channels:
          division[codec][lang][channel] = []
          for _ in range(len(all_aud_playlists)):
            division[codec][lang][channel].append(None)
    
    # Fill the division map.
    for i, aud_playlists in enumerate(all_aud_playlists):
      for aud_playlist in aud_playlists:
        assert isinstance(aud_playlist.codec, AudioCodec)
        division[aud_playlist.codec][aud_playlist.stream_info.get(
          'LANGUAGE', '"und"')][aud_playlist.channels][i] = aud_playlist
    
    # Substitute for any missing languages in the divison map.
    for i in range(len(all_aud_playlists)):
      for codec in codecs:
        for lang in langs:
          # If all the channels are None for this language in period i,
          # then we are missing the language.
          if all(division[codec][lang][channel][i] is None for channel in channels):
            # Get a substitute language.
            sub_lang = MediaPlaylist._fit_missing_lang(
              _non_nones([division[codec][lg][ch][i]
                          for lg in langs for ch in channels]), lang)
            for channel in channels:
              # Replace the missing language with the substitute.
              division[codec][lang][channel][i] = division[codec][sub_lang][channel][i]
    
    sorted_channels = sorted(channels)
    # Substitute for the lowest missing channel in the division map.
    for i in range(len(all_aud_playlists)):
      for codec in codecs:
        for lang in langs:
          # If None was found for the lowest channel, get the nearest higher one.
          if division[codec][lang][sorted_channels[0]][i] is None:
            for sub_channel in sorted_channels:
              if division[codec][lang][sub_channel][i]:
                division[codec][lang][sorted_channels[0]][i] = division[
                  codec][lang][sub_channel][i]
                break
          # This assertion verifies the cast done below, if we are sure that all the
          # lower channels are not None, so the higher channels won't be None too.
          assert division[codec][lang][sorted_channels[0]][i] is not None
    
    # Substitute for the rest of the missing channels in the divsion map.
    for i in range(len(all_aud_playlists)):
      for codec in codecs:
        for lang in langs:
          for ch_ind in range(1, len(sorted_channels)):
            # If None was found for this channel count, use the one just before it.
            if division[codec][lang][sorted_channels[ch_ind]][i] is None:
              division[codec][lang][sorted_channels[ch_ind]][i] = division[
                codec][lang][sorted_channels[ch_ind - 1]][i]
  
    # This cast is safe, since we made the needed assertions while mapping the
    # lowest channel for every codec-language division.
    return cast(Dict[AudioCodec,
                     Dict[str,
                          Dict[int,
                               List[MediaPlaylist]]]], division)
  
  @staticmethod
  def concat_aud(all_aud_playlists: List[List['MediaPlaylist']]
                 ) -> List['MediaPlaylist']:
    """Concatenates multiple audio playlists into one multi-period playlist for
    different languages and codecs."""

    division = MediaPlaylist.concat_aud_common(all_aud_playlists)
    
    concat_aud_playlists: List[MediaPlaylist] = []
    for codec, lang_channel_div in division.items():
      for lang, channel_div in lang_channel_div.items():
        for channel, aud_playlists in channel_div.items():
          stream_info = MediaPlaylist._keep_similar_stream_info(
            aud_playlists)
          # Put the language in case it was removed.
          if lang != '"und"':
            stream_info['LANGUAGE'] = lang
          # Get a unique file name.
          stream_info['NAME'], stream_info['URI'] = MediaPlaylist._next_unq_name()
          # Get the max channels for this playlist.
          stream_info['CHANNELS'] = MediaPlaylist._max_channels(aud_playlists)
          concat_aud_playlist = MediaPlaylist(stream_info)
          # Set the target duration.
          concat_aud_playlist.target_duration = MediaPlaylist._max_targer_dur(
            aud_playlists)
          for aud_playlist in aud_playlists:
            concat_aud_playlist.content += aud_playlist.content
            # Add a discontinuity after each period.
            concat_aud_playlist.content += '#EXT-X-DISCONTINUITY\n'
          concat_aud_playlists.append(concat_aud_playlist)
    
    return concat_aud_playlists
  
  @staticmethod
  def concat_aud_only(all_aud_playlists: List[List['MediaPlaylist']],
                      all_inf_playlists: List[List['MediaPlaylist']],
                      durations: List[float]) -> List['MediaPlaylist']:
    """Concatenates audio only periods with other audio only periods."""
    
    # Pair audio media streams with their equivalent variant streams to
    # retrieve them back later.
    pair: Dict[MediaPlaylist, MediaPlaylist] = {}
    for aud_playlists, inf_playlists in zip(all_aud_playlists, all_inf_playlists):
      for aud_playlist in aud_playlists:
        # Search for the matching stream-inf.
        for inf_playlist in inf_playlists:
          if inf_playlist.stream_info['URI'] == aud_playlist.stream_info['URI']:
            pair[aud_playlist] = inf_playlist
            break
    
    division = MediaPlaylist.concat_aud_common(all_aud_playlists)
    
    concat_aud_only_playlists: List[MediaPlaylist] = []
    for codec, lang_channel_div in division.items():
      for lang, channel_div in lang_channel_div.items():
        for channel, aud_playlists in channel_div.items():
          stream_info = MediaPlaylist._keep_similar_stream_info(
            aud_playlists)
          # Put the language in case it was removed.
          if lang != '"und"':
            stream_info['LANGUAGE'] = lang
          # Get a unique file name.
          stream_info['NAME'], stream_info['URI'] = MediaPlaylist._next_unq_name()
          # Get the max channels for this playlist.
          stream_info['CHANNELS'] = MediaPlaylist._max_channels(aud_playlists)
          concat_aud_playlist = MediaPlaylist(stream_info)
          stream_info = MediaPlaylist._keep_similar_stream_info(
            [pair[aud_playlist] for aud_playlist in aud_playlists])
          stream_info['URI'] = concat_aud_playlist.stream_info['URI']
          # Get the peak and average bandwidth for this language-channel pair.
          (stream_info['BANDWIDTH'],
           stream_info['AVERAGE-BANDWIDTH']) = MediaPlaylist._get_bandwidth(
             [pair[aud_playlist] for aud_playlist in aud_playlists],
             durations)
          # Get the codecs for the associated stream-infs.
          stream_info['CODECS'] = MediaPlaylist._get_codec(
            [pair[aud_playlist] for aud_playlist in aud_playlists])
          concat_inf_playlist = MediaPlaylist(stream_info)
          # Set the target duration.
          concat_aud_playlist.target_duration = MediaPlaylist._max_targer_dur(
            aud_playlists)
          for aud_playlist in aud_playlists:
            concat_aud_playlist.content += aud_playlist.content
            # Add a discontinuity after each period.
            concat_aud_playlist.content += '#EXT-X-DISCONTINUITY\n'
          # The media and the inf stream will be exactly the same.
          concat_inf_playlist.target_duration = concat_aud_playlist.target_duration
          concat_inf_playlist.content = concat_aud_playlist.content
          concat_aud_only_playlists.extend(
            (concat_aud_playlist, concat_inf_playlist))
    
    return concat_aud_only_playlists

  @staticmethod
  def concat_vid(all_inf_playlists: List[List['MediaPlaylist']],
                 durations: List[float]) -> List['MediaPlaylist']:
    """Concatenates multiple video playlists into one multi-period playlist for many
    resolutions and codecs, it matches the codecs first, then matches the resolutions.
    It will pick the closest lower resolution for some period(input) if the a high
    resolution was not available."""
    
    # Get all possible video codecs. We should not use the codecs that are present
    # in the pipeline config, because for some codecs we might have given the packager
    # the 'dash_only' flag.
    codecs: Set[VideoCodec] = set()
    # Get all the available resolutions.
    resolutions: Set[VideoResolution] = set()
    for inf_playlists in all_inf_playlists:
      for inf_playlist in inf_playlists:
        assert isinstance(inf_playlist.codec, VideoCodec)
        codecs.add(inf_playlist.codec)
        resolutions.add(inf_playlist.resolution)
    
    # Create and initialize a division map.
    division: Dict[VideoCodec,
                   Dict[VideoResolution,
                        List[MediaPlaylist]]] = {}
    for codec in codecs:
      division[codec] = {}
      for resolution in resolutions:
        division[codec][resolution] = []
    
    # In each period do the following:
    for inf_playlists in all_inf_playlists:
      # Initialize a mapping between video codecs and a list of resolutions available.
      codec_division: Dict[VideoCodec, List[MediaPlaylist]] = {}
      for codec in codecs:
        codec_division[codec] = []
      # For every video playlist in this period, append it to the matching
      # codec.
      for inf_playlist in inf_playlists:
        assert isinstance(inf_playlist.codec, VideoCodec)
        codec_division[inf_playlist.codec].append(inf_playlist)
      for codec in codecs:
        # Sort the variants from low resolution to high resolution.
        codec_division[codec].sort(key=lambda pl: pl.resolution)
        for i, resolution in enumerate(sorted(resolutions)):
          division[codec][resolution].append(
            # Append the ith resolution if found, else, append the max available
            # resolution.
            codec_division[codec][min(i, len(codec_division[codec]) - 1)])
    
    concat_vid_playlists: List[MediaPlaylist] = []
    for codec, resolution_division in division.items():
      for resolution, inf_playlists in resolution_division.items():
        stream_info: Dict[str, str] = MediaPlaylist._keep_similar_stream_info(
        inf_playlists)
        # Get a unique uri, stream-infs don't have a name attribute.
        _, stream_info['URI'] = MediaPlaylist._next_unq_name()
        # Get the peak and average bandwidth for this codec-resolution pair.
        (stream_info['BANDWIDTH'],
         stream_info['AVERAGE-BANDWIDTH']) = MediaPlaylist._get_bandwidth(
           inf_playlists, durations)
        # Get all the codecs that will be inside the new variant.
        stream_info['CODECS'] = MediaPlaylist._get_codec(inf_playlists)
        concat_vid_playlist = MediaPlaylist(stream_info)
        concat_vid_playlist.target_duration = MediaPlaylist._max_targer_dur(
          inf_playlists)
        for inf_playlist in inf_playlists:
          concat_vid_playlist.content += inf_playlist.content
          # Add a discontinuity after each period.
          concat_vid_playlist.content += '#EXT-X-DISCONTINUITY\n'
        concat_vid_playlists.append(concat_vid_playlist)
    
    return concat_vid_playlists

class MasterPlaylist:
  """A class representing a master playlist."""
  
  header = ''
  """A common header for MasterPlaylist objects."""
  
  def __init__(self, file: Optional[str] = None):
    """Given the path to the master playlist file, this method will read that file
    and search for MediaPlaylists inside it, and instantiate a MediaPlaylist object
    for each one found.
    
    The MediaPlaylist __init__ method will parse each media playlist and change the
    path of media segments to be relative to `MediaPlaylist.output_dir`, so make sure
    you assign this value before instantiating a MasterPlaylist object.
    
    if `file` is None, an empty MasterPlaylist object is returned."""
    
    self.playlists: List[MediaPlaylist] = []
    self.duration = 0.0
    
    if file is None:
      # Do not read. The variant streams will be appended manually.
      return
    
    dir_name = os.path.dirname(file)
    with open(file, 'r') as master_playlist:
      line = master_playlist.readline()
      while line:
        if line.startswith('#EXT-X-MEDIA'):
          stream_info = _extract_attributes(line)
          self.playlists.append(MediaPlaylist(stream_info, dir_name))
        elif line.startswith('#EXT-X-STREAM-INF'):
          stream_info = _extract_attributes(line)
          # Quote the URI to keep consistent, as the URIs in EXT-X-MEDIA are quoted too.
          stream_info['URI'] = _quote(master_playlist.readline().strip())
          self.playlists.append(MediaPlaylist(stream_info, dir_name))
        line = master_playlist.readline()
      # Get the master playlist duration from an arbitrary stream.
      self.duration = self.playlists[-1].duration
  
  def write(self, file: str, comment: str) -> None:
    """Writes the master playlist and the nested media playlists in 
    the file system."""
    
    dir_name = os.path.dirname(file)
    with open(file, 'w') as master_playlist:
      content = MasterPlaylist.header
      content += comment
      # Write #EXT-X-MEDIA playlists first.
      for media_playlist in self.playlists:
        if media_playlist.stream_info.get('TYPE'):
          media_playlist.write(dir_name)
          content += '#EXT-X-MEDIA:' + ','.join(
            [key + '=' + value 
             for key, value in media_playlist.stream_info.items()]) + '\n'
      content += '\n'
      # Then write #EXT-X-STREAM-INF playlists.
      for media_playlist in self.playlists:
        if media_playlist.stream_info.get('TYPE') is None:
          media_playlist.write(dir_name)
          # Pop out the URI, we don't write the URI in stream-infs.
          uri = _unquote(media_playlist.stream_info.pop('URI'))
          content += '#EXT-X-STREAM-INF:' + ','.join(
            [key + '=' + value
             for key, value in media_playlist.stream_info.items()]) + '\n'
          content += uri + '\n'
      master_playlist.write(content)
  
  @staticmethod
  def extract_headers(file_path: str) -> None:
    """Store the common header for the master playlist in MasterPlaylist.header variable.
    This also calles MediaPlaylist.extract_header() if any media playlist was found."""
    
    MasterPlaylist.header = ''
    with open(file_path, 'r') as master_playlist:
      line = master_playlist.readline()
      # Store each line in header until one of these tags is encountered.
      while line and not line.startswith(('#EXT-X-MEDIA', '#EXT-X-STREAM-INF')):
          # lstrip() will convert empty lines -> '' but will keep non-empty lines unchanged.
          MasterPlaylist.header += line.lstrip()
          line = master_playlist.readline()
      else:
        # Use this variant to also save the MediaPlaylist header.
        if line.startswith('#EXT-X-MEDIA'):
          uri = _unquote(_extract_attributes(line)['URI'])
        elif line.startswith('#EXT-X-STREAM-INF'):
          uri = master_playlist.readline().strip()
        MediaPlaylist.extract_header(os.path.join(
          os.path.dirname(file_path), uri))

  @staticmethod
  def concat_master_playlists(
    master_playlists: List['MasterPlaylist']) -> 'MasterPlaylist':
    
    all_txt_playlists: List[List['MediaPlaylist']] = []
    all_aud_playlists: List[List['MediaPlaylist']] = []
    all_inf_playlists: List[List['MediaPlaylist']] = []
    # The durations will be used to insert a gap in subtitles playlists when
    # there is no applicable media to insert. Will also be used to calculate
    # the average bandwidth.
    durations: List[float] = []
    
    for master_playlist in master_playlists:
      
      txt_playlists: List['MediaPlaylist'] = []
      aud_playlists: List['MediaPlaylist'] = []
      inf_playlists: List['MediaPlaylist'] = []
      
      for media_playlist in master_playlist.playlists:
        stream_type = media_playlist.stream_info.get('TYPE', 'STREAM-INF')
        if stream_type == 'SUBTITLES':
          txt_playlists.append(media_playlist)
        elif stream_type == 'AUDIO':
          aud_playlists.append(media_playlist)
        elif stream_type == 'STREAM-INF':
          inf_playlists.append(media_playlist)
        else:
          raise RuntimeError("TYPE={} is not regonized.".format(stream_type))  
      
      all_txt_playlists.append(txt_playlists)
      all_aud_playlists.append(aud_playlists)
      all_inf_playlists.append(inf_playlists)
      durations.append(master_playlist.duration)
    
    master_hls = MasterPlaylist()
    master_hls.playlists.extend(
      MediaPlaylist.concat_sub(all_txt_playlists, durations))
    
    if all(not MediaPlaylist.inf_is_vid(inf_pl) for inf_pl in all_inf_playlists):
      # When the playlist is audio only, each audio is referenced two times,
      # once in a #EXT-X-MEDIA tag and another time in a #EXT-X-STREAM-INF tag.
      # If the user has an audio-only content, the concatenation will go a little
      # bit different to produce the desired output.
      master_hls.playlists.extend(
        MediaPlaylist.concat_aud_only(
          all_aud_playlists,
          all_inf_playlists,
          durations))
    else:
      master_hls.playlists.extend(
        MediaPlaylist.concat_aud(all_aud_playlists))
      master_hls.playlists.extend(
        MediaPlaylist.concat_vid(all_inf_playlists, durations))
    
    return master_hls

class HLSConcater:
  """A class that serves as an API for the m3u8 concatenation methods."""
  
  def __init__(self,
               sample_master_playlist_path: str,
               output_dir: str):
    
    # Save common master playlist header, this will call the MediaPlaylist.extract_header
    # to save the common media playlist header as well.
    MasterPlaylist.extract_headers(sample_master_playlist_path)
    # Give the MediaPlaylist class the output directory so it can calculate the
    # relative direcoty to each media segment.
    MediaPlaylist.output_dir = output_dir
    # Will be used when writing the concated playlists.
    self._output_dir = output_dir
    self._all_master_playlists: List[MasterPlaylist] = []
    self._concated_hls = MasterPlaylist()
    
  def add(self, master_playlist_path: str) -> None:
    
    self._all_master_playlists.append(MasterPlaylist(master_playlist_path))
  
  def concat(self) -> None:
    
    self._concated_hls = MasterPlaylist.concat_master_playlists(
      self._all_master_playlists)
  
  def write(self, concated_file_name: str, comment: str = ''):
    
    if comment:
      comment = '## ' + comment + '\n\n'
    self._concated_hls.write(os.path.join(self._output_dir,
                                          concated_file_name), comment)

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

def _codec_resolution_channels_regex(filename: str) -> Tuple[str, str]:
  """Gets the codec name and (resolution name or channel count) from a file name,
  it depends on the choice of output file names used by Shaka-Streamer."""
  
  # Search for an audio codec.
  match = (re.search(r'audio_[-a-zA-Z]+_(\d+)c_[\d\.]+[kM]?_(.*?)(?:_\d+)?\..*', filename)
  # Search for a video codec if no audio codec was found.
           or re.search(r'video_(.*?)_[\d\.]+[kM]?_(.*?)(?:_\d+)?\..*', filename))
  if match:
    return match.group(1), match.group(2)
  
  # It must be a text stream then.
  return '', ''

def _non_nones(items: List[Optional[MediaPlaylist]]) -> List[MediaPlaylist]:
  """Return the elements of the list which are not None."""
  
  return [item for item in items if item is not None]
