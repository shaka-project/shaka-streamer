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

import math
import os
import re
from enum import Enum
from typing import List, Optional, Dict, Set, Tuple
from streamer.bitrate_configuration import VideoCodec, AudioCodec, VideoResolution


class MediaPlaylist:
  """A class representing a media playlist, the information collected from the 
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
    self.codec: Optional[Enum] = None
    
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
          attribs = _search_attributes(line)
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
          # Like ENCRYPTIONKEYS, DISCONTINUITIES, COMMENTS, etc....
          self.content += line
        line = media_playlist.readline()
    self._set_codec_res_channels(self.content)
  
  def write(self, dir_name: str) -> None:
    with open(os.path.join(
      dir_name, _unquote(self.stream_info['URI'])), 'w') as media_playlist:
      content = MediaPlaylist.header
      content += '#EXT-X-TARGETDURATION:' + str(self.target_duration) + '\n'
      content += self.content
      content += '#EXT-X-ENDLIST\n'
      media_playlist.write(content)
  
  @staticmethod
  def save_header_from_file(file_path: str) -> None:
    MediaPlaylist.header = ''
    with open(file_path, 'r') as media_playlist:
      line = media_playlist.readline()
      while line:
        # Capture the M3U tag, PlaylistType, and ExtVersion.
        if line.startswith(MediaPlaylist.HEADER_TAGS):
          MediaPlaylist.header += line
        line = media_playlist.readline()
  
  def _set_codec_res_channels(self, content: str) -> None:
    """Get the audio and video codecs from file names, this will be used for the
    codec matching process in the concater, but the codecs that will be written in
    the final concated files will be the codecs from stream_info dictionary."""
    
    # We can't depend on the stream_info['CODECS'] to get the codecs from because 
    # this is only present for STREAM-INF as per Shaka-Packager's output this makes 
    # it harder to get codecs for audio segments. Also if we try to get the audio
    # codecs from one of the #EXT-X-STREAM-INF tags we will have to matche these 
    # codecs with each stream, for example a codec attribute might be like 
    # CODECS="avc1,ac-3,mp4a,opus", the video codec is put first then the audio codecs
    # are put in lexicographical order, which isn't nesseccary the same order of 
    # #EXT-X-MEDIA in the master playlist, thus there is no solid baseground for 
    # matching the codecs using the information in the master playlist.
    
    lines = content.split('\n')
    for i in range(len(lines)):
      # Don't use #EXT-X-MAP to get the codec, because HLS specs says
      # it is an optional tag.
      if lines[i].startswith('#EXTINF'):
        other, codec = _codec_resolution_channels_regex(
          os.path.basename(lines[i+1]))
        if codec in [codec.value for codec in AudioCodec]:
          self.codec = AudioCodec(codec)
          self.channels = int(other)
        if codec in [codec.value for codec in VideoCodec]:
          self.codec = VideoCodec(codec)
          self.resolution = VideoResolution.get_value(other)
  
  @staticmethod
  def inf_is_vid(inf_playlists: List['MediaPlaylist']) -> bool:
    """This is useful to detect whether the stream-inf playlists are video playlists.
    They could be audio playlists as #EXT-X-STREAM-INF because there were no video stream
    associated with this input."""
    
    # NOTE: Ideally, this check should be performed on all the INF-STREAM playlists
    # for this input, but Shaka-Packager's output guarantees for us that all the 
    # INF-STREAMs will be videos or all will be audios in a master playlist.
    if isinstance(inf_playlists[0].codec, VideoCodec):
      return True
    return False
  
  @staticmethod
  def _keep_similar_stream_info(opt_media_playlists: List[Optional['MediaPlaylist']]
                                ) -> Dict[str, str]:
    """A helper method, used to keep only the similar stream_info values and pop
    out the values that are different between multiple streams."""
    
    # Ignore the Nones.
    media_playlists = [media_playlist
                       for media_playlist in opt_media_playlists if media_playlist]

    # If all of them where None, just return nothing.
    if not media_playlists:
      return {}

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
  def _get_bandwidth(opt_inf_playlists: List[Optional['MediaPlaylist']],
                     # all_inf_playlists is passed so  canwe get the max bitrate
                     # of the other non-video streams.
                     all_inf_playlists: List[List['MediaPlaylist']],
                     durations: List[float]) -> Tuple[str, str]:
    """A helper method to get the bandwidth and average bandwidth for INF-STEAMs.
    BANDWIDTH = max(BANDWIDTHIS)
    AVERAGE-BANDWIDTH = sum(AVERAGE-BANDWIDTHS*DURATIONS)/sum(DURATIONS)"""
    
    # REMEMBER: len(opt_inf_playlists) = len(all_inf_playlists) = len(durations)
    band, avgband, tot_dur = 0, 0.0, 0.0
    for i, opt_inf_playlist in enumerate(opt_inf_playlists):
      if opt_inf_playlist:
        band = max(int(opt_inf_playlist.stream_info['BANDWIDTH']), band)
        avgband += int(
          opt_inf_playlist.stream_info['AVERAGE-BANDWIDTH']) * durations[i]
      else:
        band = max([int(inf_playlist.stream_info['BANDWIDTH'])
                    for inf_playlist in all_inf_playlists[i]] + [band])
        # refer to https://datatracker.ietf.org/doc/html/rfc8216#section-4.3.4.2 for
        # the definition of the average bandwidth.
        avgband += max(int(inf_playlist.stream_info['AVERAGE-BANDWIDTH'])
                       for inf_playlist in all_inf_playlists[i]) * durations[i]
      tot_dur += durations[i]
    
    return str(band), str(math.ceil(avgband/tot_dur))
  
  @staticmethod
  def _get_codec(opt_inf_playlists: List[Optional['MediaPlaylist']],
                 all_inf_playlists: List[List['MediaPlaylist']]) -> str:
    """A helper method get all the possible codecs for a variant, which is 
    all the codecs present in all the periods of that variant."""
    
    codec_strings: Set[str] = set()
    for i, opt_inf_playlist in enumerate(opt_inf_playlists):
      if opt_inf_playlist:
        codec_strings.update(_unquote(
          opt_inf_playlist.stream_info['CODECS']).split(','))
      else:
        # Get all the audio codecs for the missing period.
        codec_strings.update(codec_string for codec_string_list
                             in [_unquote(inf_playlist.stream_info['CODECS']).split(',')
                                 for inf_playlist in all_inf_playlists[i]]
                             for codec_string in codec_string_list)
    
    return _quote(','.join(codec_string 
                           for codec_string in codec_strings))
  
  @staticmethod
  def _next_stream_name() -> Tuple[str, str]:
    """Returns a unique NAME and URI."""
    
    stream_name = 'stream_' + str(MediaPlaylist.current_stream_index)
    MediaPlaylist.current_stream_index += 1
    
    return _quote(stream_name), _quote(stream_name + '.m3u8')
  
  @staticmethod
  def _max_targer_dur(opt_media_playlists: List[Optional['MediaPlaylist']]
                      ) -> int:
    """Returns the maximum target duration found in one of the given playlists."""
    
    return max(media_playlist.target_duration if media_playlist else 0
               for media_playlist in opt_media_playlists)
  
  @staticmethod
  def concat_sub(all_txt_playlists: List[List['MediaPlaylist']],
                 durations: List[float]) -> List['MediaPlaylist']:
    """A method that concatenates subtitle streams based on the language of the subtitles
    for each period, it will concatenate all the english subtitles, frensh subtitles, etc...
    and put them ordered in periods where a discontinuity is inserted between them.
    
    A `x=List['MediaPlaylists']` is returned, where `len(x)` is the total 
    number of langauges found, and the number of periods (discontinuities) in each playlist
    is `len(all_txt_playlists)`.
    
    When no subtitles are there for a specific langauge for a specific period, we add
    a shaka-streamer text says 'no subtitles' as a filler for this period's duration.
    
    All the language un-annotated streams for each period gets concatenated together."""
    
    # Extract all the languages from every stream.
    langs: Set[str] = set()
    for txt_playlists in all_txt_playlists:
      for txt_playlist in txt_playlists:
        langs.add(txt_playlist.stream_info.get('LANGUAGE', 'und'))
    
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
        # We are sure that for any langauge, there is at most one stream for it.
        division[txt_playlist.stream_info.get('LANGUAGE', 'und')][i] = txt_playlist
    
    concat_txt_playlists: List[MediaPlaylist] = []
    for lang, opt_txt_playlists in division.items():
      stream_info: Dict[str, str] = MediaPlaylist._keep_similar_stream_info(
        opt_txt_playlists)
      # Get a unique name and uri.
      stream_info['NAME'], stream_info['URI'] = MediaPlaylist._next_stream_name()
      concat_txt_playlist = MediaPlaylist(stream_info)
      # Set the target duration of the concated playlist to the max of 
      # all children playlists.
      concat_txt_playlist.target_duration = MediaPlaylist._max_targer_dur(
        opt_txt_playlists)
      for i, opt_txt_playlist in enumerate(opt_txt_playlists):
        if opt_txt_playlist:
          # If a playlist is there, append it.
          concat_txt_playlist.content += opt_txt_playlist.content
        else:
          # If the no playlist were found for this language for this period,
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
  def concat_aud(all_aud_playlists: List[List['MediaPlaylist']],
                 durations: List[float]) -> List['MediaPlaylist']:
    pass
  
  @staticmethod
  def concat_vid(all_inf_playlists: List[List['MediaPlaylist']],
                 durations: List[float]) -> List['MediaPlaylist']:
    """Concatenates multiple video playlists into one multi-period playlist for many
    resolutions and codecs, it matches the codecs first, then matches the resolutions.
    It will pick the closest lower resolution for some period(input) if the a high
    resolution was not available."""
    
    # Get all possible video codecs. We should not use the codecs that are present
    # in the pipeline config, because for some codecs we might want it 'dash_only'.
    codecs: Set[VideoCodec] = set()
    # Get all the available resolutions.
    resolutions: Set[VideoResolution] = set()
    for inf_playlists in all_inf_playlists:
      # Find the first video playlist, get the codecs in it and break.
      if MediaPlaylist.inf_is_vid(inf_playlists):
        for inf_playlist in inf_playlists:
          assert isinstance(inf_playlist.codec, VideoCodec)
          codecs.add(inf_playlist.codec)
          resolutions.add(inf_playlist.resolution)
    
    # You can imagine this division map as a 3D volume. X axis for video codecs,
    # Y axis for resolutions and on Z we have a list of periods.
    # In any selection of (x, y) values we should have the same period(video)
    # in some different video codec or/and resolution.
    # we can have None for some period if it doesn't have a video, thus
    # it is optional.
    division: Dict[VideoCodec, Dict[VideoResolution, List[Optional[MediaPlaylist]]]] = {}
    for codec in codecs:
      division[codec] = {}
      for resolution in resolutions:
        division[codec][resolution] = []
    
    for inf_playlists in all_inf_playlists:
      if MediaPlaylist.inf_is_vid(inf_playlists):
        # Initialize a mapping between video codecs and a list of resolutions
        # available.
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
          for i, resolution in enumerate(resolutions):
            division[codec][resolution].append(
              # Append the ith resolution if found, else, append the max available 
              # resolution.
              codec_division[codec][min(i, len(codec_division[codec]) - 1)])
      else:
        # If no video playlist for this period was found, append None in all
        # the codec-resolution divisions, to be replaced later with an empty gap.
        for codec in codecs:
          for resolution in resolutions:
            division[codec][resolution].append(None)

    concat_vid_playlists: List[MediaPlaylist] = []
    for codec, resolution_division in division.items():
      for resolution, opt_inf_playlists in resolution_division.items():
        stream_info: Dict[str, str] = MediaPlaylist._keep_similar_stream_info(
        opt_inf_playlists)
        # Get a unique name and uri.
        _, stream_info['URI'] = MediaPlaylist._next_stream_name()
        # Get the peak and average bandwidth for this codec-resolution pair.
        (stream_info['BANDWIDTH'],
         stream_info['AVERAGE-BANDWIDTH']) = MediaPlaylist._get_bandwidth(
           opt_inf_playlists, all_inf_playlists, durations)
        # Get all the codecs that will be inside the new variant
        # (all the codecs in the children periods).
        stream_info['CODECS'] = MediaPlaylist._get_codec(
          opt_inf_playlists, all_inf_playlists)
        concat_vid_playlist = MediaPlaylist(stream_info)
        concat_vid_playlist.target_duration = MediaPlaylist._max_targer_dur(
          opt_inf_playlists)
        for i, opt_inf_playlist in enumerate(opt_inf_playlists):
          if opt_inf_playlist:
            # If we have a video playlist, append it.
            concat_vid_playlist.content += opt_inf_playlist.content
          else:
            # Otherwise, fill that gap with durations[i].
            durations[i]
          # Add a discontinuity after each period.
          concat_vid_playlist.content += '#EXT-X-DISCONTINUITY\n'
        concat_vid_playlists.append(concat_vid_playlist)
    
    return concat_vid_playlists
  
  @staticmethod
  def concat_aud_only(all_aud_playlists: List[List['MediaPlaylist']],
                      all_inf_playlists: List[List['MediaPlaylist']],
                      duration: List[float]) -> List['MediaPlaylist']:
    pass

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
    
    self.media_playlists: List[MediaPlaylist] = []
    self.duration = 0.0
    
    if file is None:
      # Do not read. The variant streams will be appended manually.
      return
    
    dir_name = os.path.dirname(file)
    with open(file, 'r') as master_playlist:
      line = master_playlist.readline()
      while line:
        if line.startswith('#EXT-X-MEDIA'):
          stream_info = _search_attributes(line)
          self.media_playlists.append(MediaPlaylist(stream_info, dir_name))
        elif line.startswith('#EXT-X-STREAM-INF'):
          stream_info = _search_attributes(line)
          # Quote the URI to keep consistent, as the URIs in EXT-X-MEDIA are quoted too.
          stream_info['URI'] = _quote(master_playlist.readline().strip())
          self.media_playlists.append(MediaPlaylist(stream_info, dir_name))
        line = master_playlist.readline()
      # Get the master playlist duration from an arbitrary stream.
      self.duration = self.media_playlists[-1].duration
  
  def write(self, file: str, comment: str = '') -> None:
    dir_name = os.path.dirname(file)
    with open(file, 'w') as master_playlist:
      content = MasterPlaylist.header
      if comment:
        content += '## ' + comment + '\n\n'
      # Write #EXT-X-MEDIA playlists first.
      for media_playlist in self.media_playlists:
        if media_playlist.stream_info.get('TYPE'):
          media_playlist.write(dir_name)
          content += '#EXT-X-MEDIA:' + ','.join(
            [key + '=' + value 
             for key, value in media_playlist.stream_info.items()]) + '\n\n'
      # Then write #EXT-X-STREAM-INF playlists.
      for media_playlist in self.media_playlists:
        if not media_playlist.stream_info.get('TYPE'):
          media_playlist.write(dir_name)
          uri = _unquote(media_playlist.stream_info.pop('URI'))
          content += '#EXT-X-STREAM-INF:' + ','.join(
            [key + '=' + value
             for key, value in media_playlist.stream_info.items()]) + '\n'
          content += uri + '\n\n'
      master_playlist.write(content)
  
  @staticmethod
  def save_header_from_file(file_path: str) -> None:
    """Store the common header for the master playlist in MasterPlaylist.header variable.
    This also calles MediaPlaylist.save_header_from_file() if any media playlist was found."""
    
    MasterPlaylist.header = ''
    with open(file_path, 'r') as master_playlist:
      line = master_playlist.readline()
      # Store each line in header until one of these tags is encountered.
      while line and not line.startswith(('#EXT-X-MEDIA', '#EXT-X-STREAM-INF')):
          # lstrip() will convert '\n' -> '' but will keep non-empty lines unchanged.
          MasterPlaylist.header += line.lstrip()
          line = master_playlist.readline()
      else:
        # Use this variant to also save the MediaPlaylist header.
        if line.startswith('#EXT-X-MEDIA'):
          uri = _unquote(_search_attributes(line)['URI'])
        elif line.startswith('#EXT-X-STREAM-INF'):
          uri = master_playlist.readline().strip()
        MediaPlaylist.save_header_from_file(os.path.join(
          os.path.dirname(file_path), uri))

  @staticmethod
  def concat_master_playlists(
    master_playlists: List['MasterPlaylist']) -> 'MasterPlaylist':
    
    all_txt_playlists: List[List['MediaPlaylist']] = []
    all_aud_playlists: List[List['MediaPlaylist']] = []
    all_inf_playlists: List[List['MediaPlaylist']] = []
    # The durations will be used to insert a gap in media playlists when
    # there is no applicable media to insert, like when there is no subtitles
    # for a particular period or when there is no frensh audio for another.
    durations: List[float] = []
    
    for master_playlist in master_playlists:
      
      txt_playlists: List['MediaPlaylist'] = []
      aud_playlists: List['MediaPlaylist'] = []
      inf_playlists: List['MediaPlaylist'] = []
      
      for media_playlist in master_playlist.media_playlists:
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
    master_hls.media_playlists.extend(
      MediaPlaylist.concat_sub(all_txt_playlists, durations))
    
    if all(not MediaPlaylist.inf_is_vid(inf_pl) for inf_pl in all_inf_playlists):
      # When the playlist is audio only, each audio is referenced two times,
      # once in a #EXT-X-MEDIA tag and another time in a #EXT-X-STREAM-INF tag.
      # If the user has an audio-only content, the concatenation will go a little
      # bit different to produce the desired output.
      master_hls.media_playlists.extend(
        MediaPlaylist.concat_aud_only(
          all_aud_playlists,
          all_inf_playlists,
          durations))
    else:
      #master_hls.media_playlists.extend(
      #  MediaPlaylist.concat_aud(all_aud_playlists, durations))
      master_hls.media_playlists.extend(
        MediaPlaylist.concat_vid(all_inf_playlists, durations))
    
    return master_hls

def _search_attributes(line: str) -> Dict[str, str]:
  """Extracts attributes from an m3u8 #EXT-X tag to a python dictionary."""
  
  attributes: Dict[str, str] = {}
  line = line.strip().split(':', 1)[1]
  # For a tighter search, append ',' and search for it in the regex.
  line += ','
  # Search for all KEY=VALUE,
  matches: List[str] = re.findall(
    r'[-A-Z]+=(?:[-A-Z]+|[\d\.]+|\d+x\d+|\"[^\"]*\"),',
    line)
  # NOTE: This regex r'[-A-Z0-9]+=(?:[-A-Z0-9]+|\d*\.?\d*|\d+x[0-9A-F]+|\"[^\"]*\"),'
  # better follows the attribute rules in
  # https://datatracker.ietf.org/doc/html/draft-pantos-http-live-streaming-23#section-4.2
  for match in matches:
    key, value = match[:-1].split('=', 1)
    attributes[key] = value
  return attributes

def _quote(string: str) -> str:
  """Puts a string in quotes, opposite of eval."""
  
  return '"' + string + '"'

def _unquote(string: str) -> str:
  """A wrapper around eval() to provide type annotations.
  Should be used to unquote strings only, otherwise it's not safe."""
  
  return eval(string)

def _codec_resolution_channels_regex(filename: str) -> Tuple[str, str]:
  """Gets the codec name and (resolution name or channel count) from a file name,
  it depends on the choice of output file names used by Shaka-Streamer."""
  
  # Search for an audio codec.
  match = (re.search(r'audio_[a-z]+_(\d+)c_[\d\.]+[kM]?_(.*?)(?:_\d+)?\..*', filename)
  # Search for a video codec if no audio codec was found.
           or re.search(r'video_(.*?)_[\d\.]+[kM]?_(.*?)(?:_\d+)?\..*', filename))
  if match:
    return match.group(1), match.group(2)
  
  # It must be a text stream then.
  return '', ''
