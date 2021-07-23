from threading import Thread
import win32pipe, win32file, pywintypes # type: ignore

class WinFIFO(Thread):
  """A threaded class that serves as a FIFO pipe that transfers data from a
  writer to a reader process on Windows.
  
  It is a replacement for os.mkfifo on POSIX systems."""

  READER_PREFIX = r'\\.\pipe\R'
  WRITER_PREFIX = r'\\.\pipe\W'
  
  def __init__(self, pipe_name: str, buf_size = 64 * 1024):
    """Initializes a thread and creates two named pipes on the system."""

    super().__init__(daemon=True)
    self.pipe_name = pipe_name
    self.BUF_SIZE = buf_size

    # The read pipe is connected to a writer process.
    self.read_side = win32pipe.CreateNamedPipe(
    WinFIFO.WRITER_PREFIX + self.pipe_name,
    win32pipe.PIPE_ACCESS_INBOUND,
    win32pipe.PIPE_WAIT | win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE,
    1,
    self.BUF_SIZE,
    self.BUF_SIZE,
    0,
    None)

    # The write pipe is connected to a reader process.
    self.writ_side = win32pipe.CreateNamedPipe(
    WinFIFO.READER_PREFIX + self.pipe_name,
    win32pipe.PIPE_ACCESS_OUTBOUND,
    win32pipe.PIPE_WAIT | win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE,
    1,
    self.BUF_SIZE,
    self.BUF_SIZE,
    0,
    None)

  def run(self):
    """The FIFO thread. This method serves as a server that connects a writer
    client to a reader client."""

    try:
      # Connect to both ends of the pipe before starting the transfer.
      # This funciton is blocking. If no process is connected, it will wait indefinitely.
      win32pipe.ConnectNamedPipe(self.read_side)
      win32pipe.ConnectNamedPipe(self.writ_side)
      while True:
        # Writer -> read_side -> writ_side -> Reader
        _, data = win32file.ReadFile(self.read_side, self.BUF_SIZE)
        win32file.WriteFile(self.writ_side, data)
    except Exception as ex:
      # Remove the pipes from the system.
      win32file.CloseHandle(self.read_side)
      win32file.CloseHandle(self.writ_side)
      # If the error was due to one of the processes shutting down, just exit normally.
      if isinstance(ex, pywintypes.error) and (ex.args[0] == 109 or ex.args[0] == 232):
        return 0
      # Otherwise, raise that error.
      raise ex
