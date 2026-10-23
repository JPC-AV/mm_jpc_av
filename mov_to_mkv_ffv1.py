#!/usr/bin/env python3
"""
MOV to MKV Conversion Script - converts v210/mov files to ffv1/mkv preservation format.

Converts v210/mov files to FFV1/MKV preservation copies and H.264/MP4 access derivatives,
organizing outputs into directories named after each source file.
"""

import subprocess
import sys
import argparse
import time
import os
import re
import signal
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

# ==============================
# TERMINAL COLORS
# ==============================

class Colors:
    """ANSI color codes for terminal output."""
    BOLD = '\033[1m'
    DIM = '\033[2m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    MAGENTA = '\033[95m'
    WHITE = '\033[97m'
    RESET = '\033[0m'
    
    @classmethod
    def disable(cls):
        """Disable colors (for non-TTY output)."""
        for attr in ['BOLD', 'DIM', 'CYAN', 'GREEN', 'YELLOW', 'RED', 'MAGENTA', 'WHITE', 'RESET']:
            setattr(cls, attr, '')

# Disable colors if not a TTY
if not sys.stdout.isatty():
    Colors.disable()

# Exit statuses (see EXIT STATUS in the help)
EXIT_OK = 0           # every file converted or skipped; a dry run finished
EXIT_FAILED = 1       # a conversion failed, or the run could not go on
EXIT_INTERRUPTED = 130  # Ctrl-C; a stop signal gives 128 + its number (SIGTERM 143, SIGHUP 129)

# How long a still-running ffmpeg is given to exit after SIGTERM before SIGKILL
STOP_GRACE_SECONDS = 10

# A log that still says this after the run: it stopped before finishing that file
IN_PROGRESS = "IN PROGRESS (if this is still here, the run stopped before finishing this file)"


class StopRequested(KeyboardInterrupt):
    """SIGTERM or SIGHUP sent to this command: handled like Ctrl-C, so the
    running ffmpeg is stopped and the log says INTERRUPTED."""

    def __init__(self, signum: int):
        super().__init__()
        self.signum = signum


def _stop_requested(signum, frame):
    raise StopRequested(signum)


def stop_reason(interrupt: KeyboardInterrupt) -> str:
    """Ctrl-C, or the stop signal's name (SIGTERM, SIGHUP)."""
    if isinstance(interrupt, StopRequested):
        return signal.Signals(interrupt.signum).name
    return "Ctrl-C"


# ==============================
# FFMPEG VERSION CHECK
# ==============================

def check_ffmpeg_version() -> Optional[str]:
    """The FFmpeg version, e.g. "7.1"; "" when it could not be read; None when
    ffmpeg is not found or cannot be run. (-apply_cropping needs 7.1 or later.)"""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            errors="replace"
        )
    except OSError:
        return None
    # Parse version from first line, e.g., "ffmpeg version 7.1 Copyright..."
    match = re.search(r'ffmpeg version (\d+)\.(\d+)', result.stdout)
    if match:
        return f"{int(match.group(1))}.{int(match.group(2))}"
    return ""


# ==============================
# LOGGING
# ==============================

class ConversionLog:
    """Handles per-file logging for conversion process."""
    
    def __init__(self, log_path: Path, source_file: Path, replace: bool = False):
        self.log_path = log_path
        self.source_file = source_file
        self.replace = replace      # may an existing log be replaced (--overwrite/--overwrite-all)
        self.written = False        # this run has written the log (later saves replace it)
        self.start_time = datetime.now()
        self.lines = []
        
        # Header
        self._add_header()
    
    def _add_header(self):
        """Add log header with source file info."""
        self.lines.append("=" * 70)
        self.lines.append("MOV to MKV Conversion Log")
        self.lines.append("=" * 70)
        self.lines.append("")
        self.lines.append(f"Timestamp:    {self.start_time.isoformat()}")
        self.lines.append(f"Source file:  {self.source_file}")
        
        # Get source file size
        try:
            size_bytes = self.source_file.stat().st_size
            size_gb = size_bytes / (1024 ** 3)
            self.lines.append(f"Source size:  {size_bytes:,} bytes ({size_gb:.2f} GB)")
        except OSError:
            self.lines.append("Source size:  (unable to read)")
        
        self.lines.append("")
    
    def log_command(self, label: str, cmd: list):
        """Log an ffmpeg command."""
        self.lines.append("-" * 70)
        self.lines.append(f"{label}")
        self.lines.append("-" * 70)
        self.lines.append("")
        self.lines.append("Command:")
        self.lines.append(f"  {' '.join(cmd)}")
        self.lines.append("")
    
    def log_output(self, stdout: str, stderr: str):
        """Log ffmpeg stdout/stderr."""
        if stdout and stdout.strip():
            self.lines.append("STDOUT:")
            for line in stdout.strip().split('\n'):
                self.lines.append(f"  {line}")
            self.lines.append("")
        
        if stderr and stderr.strip():
            self.lines.append("STDERR:")
            for line in stderr.strip().split('\n'):
                self.lines.append(f"  {line}")
            self.lines.append("")
    
    def log_result(self, success: bool, output_file: Optional[Path] = None, error_msg: Optional[str] = None):
        """Log the result of a conversion step."""
        if success:
            self.lines.append(f"Result: SUCCESS")
            if output_file and output_file.exists():
                size_bytes = output_file.stat().st_size
                size_gb = size_bytes / (1024 ** 3)
                self.lines.append(f"Output size:  {size_bytes:,} bytes ({size_gb:.2f} GB)")
        else:
            self.lines.append(f"Result: FAILED")
            if error_msg:
                self.lines.append(f"Error: {error_msg}")
        self.lines.append("")
    
    def log_note(self, text: str):
        """Log a line that is not a command or its result."""
        self.lines.append(text)
        self.lines.append("")

    def finalize(self, status: str) -> Optional[str]:
        """Add footer and write log to disk. Called first with IN_PROGRESS,
        before ffmpeg starts, then with SUCCESS, FAILED or INTERRUPTED. The
        first write replaces an existing log only when this run may
        (self.replace); otherwise it creates a new file ('x' never replaces a
        file that appeared meanwhile). -> None, or why it was not written."""
        end_time = datetime.now()
        elapsed = end_time - self.start_time
        
        footer = ["=" * 70, "Summary", "=" * 70, ""]
        if status != IN_PROGRESS:
            footer.append(f"Completed:    {end_time.isoformat()}")
            footer.append(f"Elapsed:      {elapsed}")
        footer.append(f"Status:       {status}")
        footer.append("")
        
        # Write to file
        try:
            with open(self.log_path, 'w' if (self.replace or self.written) else 'x') as f:
                f.write('\n'.join(self.lines + footer))
        except OSError as e:
            return e.strerror or type(e).__name__
        self.written = True
        return None

# ==============================
# HELP FORMATTING
# ==============================

def get_colored_help():
    """Generate a colored and formatted help message for the command line."""
    C = Colors
    
    help_text = f"""
{C.BOLD}{C.CYAN}╔══════════════════════════════════════════════════════════════════════════════╗
║                    MOV to MKV Conversion Script                              ║
╚══════════════════════════════════════════════════════════════════════════════╝{C.RESET}

{C.BOLD}{C.WHITE}DESCRIPTION{C.RESET}
    Converts v210/mov files to preservation and access formats:
    {C.GREEN}1.{C.RESET} FFV1/MKV preservation copy → {C.YELLOW}lossless, archival format{C.RESET}
    {C.GREEN}2.{C.RESET} H.264/MP4 access derivative → {C.YELLOW}small, streamable for review{C.RESET}
    {C.GREEN}3.{C.RESET} Organizes outputs into {C.YELLOW}directories named by source file{C.RESET}
    Source .mov files are kept as they are (not moved, changed or deleted).

{C.BOLD}{C.WHITE}USAGE{C.RESET}
    {C.GREEN}${C.RESET} python3 mov_to_mkv_ffv1.py [-d PATH | --single FILE [FILE ...]] [options]

{C.BOLD}{C.WHITE}OPTIONS{C.RESET}
    {C.CYAN}-d, --directory PATH{C.RESET}       Every .mov/.MOV file in PATH (not subfolders)
    {C.CYAN}--single FILE [FILE ...]{C.RESET}   Process specific .mov file(s) directly
    {C.CYAN}-n, --dry-run{C.RESET}              Preview: create nothing, run no ffmpeg
    {C.CYAN}--no-access{C.RESET}                No access derivative (an existing one is ignored)
    {C.CYAN}--overwrite{C.RESET}                Replace an existing .mkv and log; keep an
                               existing access file (not remade or checked)
    {C.CYAN}--overwrite-all{C.RESET}            Replace every existing output, access too
    {C.CYAN}--progress{C.RESET}                 Show ffmpeg's progress while encoding
    {C.CYAN}--no-color{C.RESET}                 Disable colored output

{C.BOLD}{C.WHITE}EXISTING OUTPUTS{C.RESET}
    Without --overwrite or --overwrite-all nothing is replaced: a .mov with
    any output already there (.mkv, conversion log, or access .mp4 unless
    --no-access) is skipped before conversion, naming the files in the way.
    A dry run makes the same skip, convert, replace and keep decisions
    (a real run can still fail).

{C.BOLD}{C.WHITE}EXIT STATUS{C.RESET}
    {C.YELLOW}0{C.RESET}    every file converted or skipped; a dry run finished
    {C.YELLOW}1{C.RESET}    a conversion failed, an output folder or log could not be
         written, the screen or progress output failed, ffmpeg is missing or
         older than 7.1, or a named file or folder was not found
    {C.YELLOW}2{C.RESET}    the command line was refused
    {C.YELLOW}130{C.RESET}  interrupted (Ctrl-C): the file in progress is incomplete
    {C.YELLOW}143{C.RESET}  stopped by SIGTERM ({C.YELLOW}129{C.RESET}: SIGHUP), the same way as Ctrl-C

{C.BOLD}{C.WHITE}EXAMPLES{C.RESET}
    {C.GREEN}${C.RESET} python3 mov_to_mkv_ffv1.py -d /path/to/mov/files
    {C.GREEN}${C.RESET} python3 mov_to_mkv_ffv1.py -d /path/to/mov/files --dry-run
    {C.GREEN}${C.RESET} python3 mov_to_mkv_ffv1.py --single /path/to/JPC_AV_00001.mov
    {C.GREEN}${C.RESET} python3 mov_to_mkv_ffv1.py --single file1.mov file2.mov --no-access

{C.BOLD}{C.WHITE}INPUT/OUTPUT{C.RESET}
    {C.DIM}Input:{C.RESET}  {C.MAGENTA}JPC_AV_00001.mov{C.RESET}
    {C.DIM}Output:{C.RESET} {C.GREEN}JPC_AV_00001/{C.RESET}
               ├── {C.GREEN}JPC_AV_00001.mkv{C.RESET}             {C.DIM}(FFV1/FLAC preservation){C.RESET}
               ├── {C.GREEN}JPC_AV_00001_access.mp4{C.RESET}      {C.DIM}(H.264/AAC access){C.RESET}
               └── {C.GREEN}JPC_AV_00001_conversion.log{C.RESET}  {C.DIM}(conversion log){C.RESET}

{C.BOLD}{C.WHITE}TECHNICAL NOTES{C.RESET}
    {C.DIM}•{C.RESET} Meant for NTSC SD v210 .mov transfers: 720x486, interlaced, bottom
      field first, with audio. Nothing checks this: other files are mislabelled
      or fail.
    {C.DIM}•{C.RESET} Uses {C.CYAN}-apply_cropping 0{C.RESET} to preserve full frame (720x486); needs FFmpeg 7.1+
    {C.DIM}•{C.RESET} FFV1 settings: level 3, slicecrc 1, 24 slices (as committed - validate);
      video and audio streams only (timecode, data, subtitle and caption tracks
      are dropped); marked bottom field first; FLAC audio
    {C.DIM}•{C.RESET} The .mkv's creation_time is the UTC time its conversion started
    {C.DIM}•{C.RESET} Access derivative: CRF 28, fast preset (optimized for remote viewing)
    {C.DIM}•{C.RESET} A failed or interrupted conversion leaves its output incomplete (never
      deleted, never reported complete): read its log, then rerun that file with
      --overwrite - or --overwrite-all if its access step failed or was
      interrupted, since --overwrite keeps an existing access file
    {C.DIM}•{C.RESET} An interruption normally stops ffmpeg too, but one that lands while
      ffmpeg is still starting can escape that: afterwards, check that no
      ffmpeg is still running, and treat that file's outputs as incomplete,
      before retrying
    {C.DIM}•{C.RESET} Before real use, check the settings against the batch and validate a
      representative conversion (see the README)
"""
    return help_text


def get_short_usage():
    """Generate short usage for error messages."""
    C = Colors
    
    usage = f"""
usage: mov_to_mkv_ffv1.py [-d PATH | --single FILE [FILE ...]] [options]
       {C.DIM}Use -h or --help for detailed information{C.RESET}

  {C.CYAN}-d, --directory PATH{C.RESET}       Every .mov file in PATH (not subfolders)
  {C.CYAN}--single FILE [FILE ...]{C.RESET}   Process specific .mov file(s) directly
  {C.CYAN}-n, --dry-run{C.RESET}              Preview: create nothing, run no ffmpeg
  {C.CYAN}--no-access{C.RESET}                No H.264/MP4 access derivative
  {C.CYAN}--overwrite{C.RESET}                Replace .mkv and log; keep existing access file
  {C.CYAN}--overwrite-all{C.RESET}            Replace every existing output
  {C.CYAN}--progress{C.RESET}                 Show ffmpeg's progress while encoding
  {C.CYAN}--no-color{C.RESET}                 Disable colored output
"""
    return usage


# ==============================
# CONVERSION FUNCTIONS
# ==============================

def print_status(status: str, message: str, indent: int = 0):
    """Print a colorized status message."""
    C = Colors
    indent_str = "  " * indent
    
    symbols = {
        "success": f"{C.GREEN}✓{C.RESET}",
        "error": f"{C.RED}✗{C.RESET}",
        "warning": f"{C.YELLOW}!{C.RESET}",
        "info": f"{C.CYAN}→{C.RESET}",
        "skip": f"{C.DIM}○{C.RESET}",
    }
    symbol = symbols.get(status, " ")
    print(f"{indent_str}{symbol} {message}")


def plan_file(mov_file: Path, no_access: bool, overwrite: bool, overwrite_all: bool) -> dict:
    """What a run does with one .mov file - the same decision for a dry run
    and a real run:
      default          any planned output already there -> skip the file
      --overwrite      replace the .mkv and the log; keep an existing access
                       derivative (not remade), make a missing one
      --overwrite-all  replace every planned output
      --no-access      the access derivative is not planned, looked at or made"""
    base_name = mov_file.stem  # e.g., "JPC_AV_00013"
    output_dir = mov_file.parent / base_name
    plan = {
        "dir": output_dir,
        "mkv": output_dir / f"{base_name}.mkv",
        "access": output_dir / f"{base_name}_access.mp4",
        "log": output_dir / f"{base_name}_conversion.log",
        "skip": None,          # why the file is skipped
        "make_access": not no_access,
        "keep_access": False,  # --overwrite and an access derivative already there
        "existing": [],        # planned outputs already there
    }
    if os.path.islink(output_dir):
        plan["skip"] = f"{output_dir.name}: a symbolic link - never written through"
        return plan
    if os.path.lexists(output_dir) and not output_dir.is_dir():
        plan["skip"] = f"{output_dir.name} exists and is not a folder"
        return plan
    planned = ["mkv", "log"] + ([] if no_access else ["access"])
    links = [plan[k].name for k in planned if os.path.islink(plan[k])]
    if links:
        plan["skip"] = (f"{', '.join(links)}: a symbolic link - never written "
                        f"through or replaced")
        return plan
    plan["existing"] = [k for k in planned if os.path.lexists(plan[k])]
    if overwrite_all:
        return plan
    if overwrite:
        if "access" in plan["existing"]:
            plan["make_access"], plan["keep_access"] = False, True
        return plan
    if plan["existing"]:
        names = ", ".join(plan[k].name for k in plan["existing"])
        hint = ("--overwrite replaces the .mkv and log but keeps the access .mp4; "
                "--overwrite-all replaces all" if "access" in plan["existing"]
                else "--overwrite or --overwrite-all replaces them")
        plan["skip"] = f"already exists: {names} - nothing replaced ({hint})"
    return plan


def ffv1_command(mov_file: Path, output_file: Path, overwrite_flag: str, creation_time: str) -> list:
    """The FFV1/MKV preservation command (the committed settings; only
    creation_time is now a concrete UTC time instead of "now")."""
    # -apply_cropping 0: Prevents FFmpeg 7.1+ from applying clap atom cropping
    #                   (preserves full 720x486 frame instead of cropping to 704x480)
    # -map 0:v -map 0:a: Maps only video and audio streams
    #                    (excludes timecode/tmcd data streams which MKV doesn't support)
    # -vf setfield=bff: Marks video as interlaced bottom-field-first
    # -top 0: Indicates BFF for codec
    # -flags +ilme+ildct: Enables interlaced motion estimation and DCT
    # -metadata creation_time=...: Sets encoded date (UTC, when this conversion starts)
    # -vtag FFV1: Forces V_MS/VFW/FOURCC codec ID for compatibility
    return [
        "ffmpeg",
        "-apply_cropping", "0",
        "-i", str(mov_file),
        "-map", "0:v",
        "-map", "0:a",
        "-c:v", "ffv1",
        "-level", "3",
        "-coder", "1",
        "-context", "1",
        "-g", "1",
        "-slicecrc", "1",
        "-slices", "24",
        "-vf", "setfield=bff",
        "-top", "0",
        "-flags", "+ilme+ildct",
        "-vtag", "FFV1",
        "-metadata", f"creation_time={creation_time}",
        "-c:a", "flac",
        "-f", "matroska",
        overwrite_flag,
        str(output_file)
    ]


def access_command(mov_file: Path, access_file: Path, overwrite_flag: str) -> list:
    """The H.264/MP4 access derivative command (the committed settings)."""
    return [
        "ffmpeg",
        "-apply_cropping", "0",
        "-i", str(mov_file),
        "-map", "0:v",
        "-map", "0:a",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "28",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        overwrite_flag,
        str(access_file)
    ]


class OutputFailed(Exception):
    """The terminal or pipe showing --progress output failed."""


class EncoderUnavailable(Exception):
    """ffmpeg could not be started (not installed, or not runnable)."""


def stop_encoder(process: subprocess.Popen):
    """Stop an ffmpeg child that is still running and wait for it, so that
    child is not left running once this command stops: SIGTERM, then SIGKILL
    if it has not exited within STOP_GRACE_SECONDS (or the wait is cut short)."""
    if process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=STOP_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    except BaseException:
        process.kill()
        process.wait()
        raise


def run_ffmpeg(cmd: list, log: ConversionLog, show_progress: bool) -> int:
    """Run one ffmpeg command and log its output. -> its return code.
    ffmpeg gets no keyboard input (stdin is the null device), so a stray
    key such as [q] cannot cut a conversion short. With show_progress its
    standard error (where ffmpeg reports progress) is shown as it arrives.
    Once Popen has returned, an interruption (Ctrl-C, SIGTERM, SIGHUP) or a
    failure of that progress output (raised as OutputFailed) stops ffmpeg
    and waits for it first. Not covered: an interruption that lands while
    ffmpeg is still being started, inside Popen - that ffmpeg can keep
    running, and this file's log may not be updated (see the README).
    EncoderUnavailable: ffmpeg could not be started."""
    try:
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace"
        )
    except OSError as e:
        raise EncoderUnavailable(e.strerror or type(e).__name__) from None
    stderr = []
    try:
        # FFmpeg outputs progress to stderr
        for line in process.stderr:
            stderr.append(line)
            if show_progress:
                try:
                    sys.stderr.write(f"       {line}")
                    sys.stderr.flush()
                except (OSError, ValueError) as e:
                    raise OutputFailed(getattr(e, "strerror", None) or type(e).__name__) from None
        return process.wait()
    finally:
        try:
            stop_encoder(process)
        finally:
            process.stderr.close()
            log.log_output("", "".join(stderr))


def _to_null(stream):
    """After an output failure: point the stream at the null device, so what
    it still holds - and Python's own flush at exit - cannot fail again."""
    try:
        null = os.open(os.devnull, os.O_WRONLY)
        try:
            os.dup2(null, stream.fileno())
        finally:
            os.close(null)
    except (OSError, ValueError, AttributeError):
        pass


class GuardedOutput:
    """Standard output for one run. The first write or flush that fails (a
    closed pipe or terminal, a full disk) is recorded in `lost`; that and
    every later write are dropped, so the failure never escapes into the
    run. The run then starts no further file, and exits 1 at most."""

    def __init__(self, stream):
        self.stream, self.lost = stream, None

    def _failed(self, error):
        self.lost = getattr(error, "strerror", None) or type(error).__name__
        _to_null(self.stream)

    def write(self, text):
        if self.lost is None:
            try:
                return self.stream.write(text)
            except (OSError, ValueError) as e:
                self._failed(e)
        return len(text)

    def flush(self):
        if self.lost is None:
            try:
                self.stream.flush()
            except (OSError, ValueError) as e:
                self._failed(e)

    def __getattr__(self, name):
        return getattr(self.stream, name)


def output_lost() -> Optional[str]:
    """Why standard output failed during this run, or None."""
    return getattr(sys.stdout, "lost", None)


def convert_files(mov_files: list, dry_run: bool = False, no_access: bool = False,
                   overwrite: bool = False, overwrite_all: bool = False,
                   show_progress: bool = False) -> dict:
    """Convert .mov files to ffv1/mkv, placing outputs in named subdirectories.
    A dry run makes the same decisions (plan_file) but creates nothing and
    runs no ffmpeg. -> the counts, and why the run stopped early ("interrupted",
    "output failed", "ffmpeg unavailable") or None; "interrupt" is the
    KeyboardInterrupt (Ctrl-C) or StopRequested (a stop signal) that did it."""
    C = Colors
    counts = {"converted": 0, "skipped": 0, "failed": 0, "interrupted": 0,
              "not_started": 0, "kept_access": 0, "stopped": None, "interrupt": None}
    
    if not mov_files:
        print_status("warning", "No .mov files to process")
        return counts
    
    print(f"\n{C.BOLD}Found {len(mov_files)} .mov file(s) to convert{C.RESET}\n")
    print(f"{C.DIM}{'─' * 60}{C.RESET}")
    
    replace_mkv = overwrite or overwrite_all
    folders = {}   # output folder (letter case ignored) -> the input that claimed it
    
    for i, mov_file in enumerate(mov_files, 1):
        sys.stdout.flush()          # what is waiting in a pipe: a failure shows now
        if output_lost() and not dry_run:
            counts["stopped"] = "output failed"
            counts["not_started"] = len(mov_files) - i + 1
            break
        file_start_time = time.time()
        plan = plan_file(mov_file, no_access, overwrite, overwrite_all)
        output_dir, output_file, access_file, log_file = (plan["dir"], plan["mkv"],
                                                          plan["access"], plan["log"])
        # Two inputs with one output folder (a file named twice, or X.mov and
        # X.MOV): only the first is converted, in a dry run as in a real one
        folder_key = str(output_dir).casefold()
        if folder_key in folders:
            plan["skip"] = (f"its output folder {output_dir.name} is also the one for "
                            f"{folders[folder_key]}, earlier in this run")
        folders.setdefault(folder_key, mov_file.name)
        
        print(f"\n{C.BOLD}[{i}/{len(mov_files)}]{C.RESET} {C.CYAN}{mov_file.name}{C.RESET}")
        print(f"       {C.DIM}→{C.RESET} {output_dir.name}/{output_file.name}")
        if not no_access:
            print(f"       {C.DIM}→{C.RESET} {output_dir.name}/{access_file.name}")
        print(f"       {C.DIM}→{C.RESET} {output_dir.name}/{log_file.name}")
        
        if plan["skip"]:
            print_status("skip", f"{'Would skip' if dry_run else 'Skipped'}: {plan['skip']}", indent=3)
            counts["skipped"] += 1
            continue
        if plan["keep_access"]:
            print_status("skip", f"{'Would keep' if dry_run else 'Keeping'} the existing "
                                 f"{access_file.name} (--overwrite keeps access derivatives; "
                                 f"not remade or checked)", indent=3)
            counts["kept_access"] += 1

        if dry_run:
            for key in ["mkv", "log"] + (["access"] if plan["make_access"] else []):
                verb = "replace" if key in plan["existing"] else "create"
                print_status("info", f"Would {verb} {plan[key].name}", indent=3)
            counts["converted"] += 1
            continue
        
        # Create output directory
        try:
            output_dir.mkdir(exist_ok=True)
        except OSError as e:
            print_status("error", f"Could not create {output_dir} "
                                  f"({e.strerror or type(e).__name__}) - not converted", indent=3)
            counts["failed"] += 1
            continue
        
        # Initialize per-file log, on disk before ffmpeg starts
        log = ConversionLog(log_file, mov_file, replace=replace_mkv)
        if plan["keep_access"]:
            log.log_note(f"Existing access derivative kept (--overwrite): {access_file}")
        problem = log.finalize(IN_PROGRESS)
        if problem:
            print_status("error", f"Could not write {log_file} ({problem}) - not converted",
                         indent=3)
            counts["failed"] += 1
            continue
        status, step = "FAILED", "FFV1/MKV"
        
        try:
            # Get current timestamp in ISO format for metadata
            creation_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000000Z")
            
            # FFV1/MKV preservation file
            ffv1_cmd = ffv1_command(mov_file, output_file, "-y" if replace_mkv else "-n",
                                    creation_time)
            log.log_command("FFV1/MKV Preservation Copy", ffv1_cmd)
            returncode = run_ffmpeg(ffv1_cmd, log, show_progress)
            if returncode == 0:
                log.log_result(True, output_file)
                print_status("success", "FFV1/MKV complete", indent=3)
            else:
                log.log_result(False, error_msg=f"ffmpeg returned {returncode}")
                print_status("error", f"FFV1 error: ffmpeg returned {returncode} - "
                                      f"{output_file.name} is not complete", indent=3)
                
            # H.264/MP4 access derivative (unless --no-access, or kept by --overwrite)
            if returncode == 0 and plan["make_access"]:
                step = "H.264/MP4 access"
                access_cmd = access_command(mov_file, access_file,
                                            "-y" if overwrite_all else "-n")
                log.log_command("H.264/MP4 Access Derivative", access_cmd)
                returncode = run_ffmpeg(access_cmd, log, show_progress)
                if returncode == 0:
                    log.log_result(True, access_file)
                    print_status("success", "H.264/MP4 access complete", indent=3)
                else:
                    log.log_result(False, error_msg=f"ffmpeg returned {returncode}")
                    print_status("error", f"Access error: ffmpeg returned {returncode} - "
                                          f"{access_file.name} is not complete (only "
                                          f"--overwrite-all remakes it)", indent=3)
                    
            if returncode == 0:
                status = "SUCCESS"
        except KeyboardInterrupt as e:      # Ctrl-C, or SIGTERM/SIGHUP (StopRequested)
            status, counts["stopped"], counts["interrupt"] = "INTERRUPTED", "interrupted", e
            log.log_result(False, error_msg=f"interrupted ({stop_reason(e)}) during the "
                                            f"{step} step - its output is incomplete")
            print_status("error", f"Interrupted ({stop_reason(e)}) during the {step} step - "
                                  f"its output is incomplete"
                                  + (" (only --overwrite-all remakes it)"
                                     if step == "H.264/MP4 access" else ""), indent=3)
        except OutputFailed as e:
            _to_null(sys.stderr)
            counts["stopped"] = "output failed"
            log.log_result(False, error_msg=f"the progress output failed ({e}) during the "
                                            f"{step} step; ffmpeg was stopped - its output "
                                            f"is incomplete")
            print_status("error", f"The progress output failed ({e}) - ffmpeg was stopped; "
                                  f"the {step} output is incomplete", indent=3)
        except EncoderUnavailable as e:
            counts["stopped"] = "ffmpeg unavailable"
            log.log_result(False, error_msg=f"ffmpeg could not be started ({e})")
            print_status("error", f"ffmpeg could not be started ({e}). Please install ffmpeg.",
                         indent=3)
        
        # Finalize log
        problem = log.finalize(status)
        if problem:
            print_status("error", f"Log NOT updated ({problem}): {log_file}", indent=3)
            if status == "SUCCESS":
                status = "FAILED"
        else:
            print_status("success" if status == "SUCCESS" else "warning",
                         f"Log saved: {log_file.name}"
                         + ("" if status == "SUCCESS" else f" (status {status})"), indent=3)
        
        # Calculate and display per-file elapsed time
        file_elapsed = time.time() - file_start_time
        file_mins, file_secs = divmod(int(file_elapsed), 60)
        file_hours, file_mins = divmod(file_mins, 60)
        file_time_str = f"{file_hours:02d}:{file_mins:02d}:{file_secs:02d}"
        print(f"       {C.DIM}Elapsed: {file_time_str}{C.RESET}")

        if status == "SUCCESS":
            counts["converted"] += 1
        elif status == "INTERRUPTED":
            counts["interrupted"] += 1
        else:
            counts["failed"] += 1
        if counts["stopped"]:
            counts["not_started"] = len(mov_files) - i
            break
    
    # Summary
    print(f"\n{C.DIM}{'─' * 60}{C.RESET}")
    print(f"\n{C.BOLD}SUMMARY{C.RESET}")
    if dry_run:
        print(f"  {C.YELLOW}DRY RUN - nothing was created and ffmpeg was not run{C.RESET}")
        print(f"  {C.DIM}Would convert:{C.RESET} {counts['converted']}")
        print(f"  {C.DIM}Would skip:{C.RESET}    {counts['skipped']}")
        if counts["kept_access"]:
            print(f"  {C.DIM}Would keep existing access derivatives:{C.RESET} {counts['kept_access']}")
    else:
        print(f"  {C.GREEN}Converted:{C.RESET}  {counts['converted']}")
        print(f"  {C.DIM}Skipped:{C.RESET}    {counts['skipped']}")
        if counts["failed"] > 0:
            print(f"  {C.RED}Failed:{C.RESET}     {counts['failed']}")
        if counts["interrupted"] > 0:
            print(f"  {C.RED}Interrupted:{C.RESET} {counts['interrupted']} (output incomplete)")
        if counts["not_started"] > 0:
            print(f"  {C.YELLOW}Not started:{C.RESET} {counts['not_started']} (the run stopped)")
        if counts["kept_access"]:
            print(f"  {C.DIM}Existing access derivatives kept (not remade or checked):{C.RESET} "
                  f"{counts['kept_access']}")

    return counts


def interrupt_status(interrupt: KeyboardInterrupt) -> int:
    """130 for Ctrl-C; 128 + the signal number for SIGTERM (143) or SIGHUP (129)."""
    if isinstance(interrupt, StopRequested):
        return 128 + interrupt.signum
    return EXIT_INTERRUPTED


def exit_status(counts: dict) -> int:
    """Interrupted: 130 (or 128 + the stop signal); 1 when a file failed or
    the run could not go on; otherwise 0 (skips are not failures)."""
    if counts["stopped"] == "interrupted":
        return interrupt_status(counts["interrupt"])
    if counts["failed"] or counts["stopped"]:
        return EXIT_FAILED
    return EXIT_OK


def finish(status: int):
    """Exit with `status` - 1 instead of 0 when standard output has failed (a
    closed pipe or terminal), never Python's 120 for a failed final flush."""
    sys.stdout.flush()
    if output_lost() and status == EXIT_OK:
        status = EXIT_FAILED
    sys.exit(status)


# ==============================
# MAIN
# ==============================

def main():
    """Main execution function."""
    sys.stdout = GuardedOutput(sys.stdout)
    
    class CustomArgumentParser(argparse.ArgumentParser):
        def format_usage(self):
            return get_short_usage()
        
        def format_help(self):
            return get_colored_help()
        
        def error(self, message):
            self.print_usage(sys.stderr)
            self.exit(2, f"\n{Colors.RED}error: {message}{Colors.RESET}\n")
    
    parser = CustomArgumentParser(
        description=get_colored_help(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
        usage=argparse.SUPPRESS
    )
    
    parser.add_argument(
        '-h', '--help',
        action='help',
        default=argparse.SUPPRESS,
        help=argparse.SUPPRESS
    )
    
    parser.add_argument(
        '-d', '--directory',
        type=str,
        required=False,
        metavar='PATH',
        help=argparse.SUPPRESS
    )
    
    parser.add_argument(
        '--single',
        nargs='+',
        metavar='FILE',
        help=argparse.SUPPRESS
    )
    
    parser.add_argument(
        '-n', '--dry-run',
        action='store_true',
        help=argparse.SUPPRESS
    )
    
    parser.add_argument(
        '--no-access',
        action='store_true',
        help=argparse.SUPPRESS
    )
    
    parser.add_argument(
        '--overwrite',
        action='store_true',
        help=argparse.SUPPRESS
    )

    parser.add_argument(
        '--overwrite-all',
        action='store_true',
        help=argparse.SUPPRESS
    )

    parser.add_argument(
        '--progress',
        action='store_true',
        help=argparse.SUPPRESS
    )

    parser.add_argument(
        '--no-color',
        action='store_true',
        help=argparse.SUPPRESS
    )
    
    args = parser.parse_args()

    # SIGTERM and SIGHUP stop a run the way Ctrl-C does: ffmpeg is stopped too.
    # A signal already ignored (SIGHUP under nohup) stays ignored.
    for name in ("SIGTERM", "SIGHUP"):
        signum = getattr(signal, name, None)
        if signum is not None and signal.getsignal(signum) != signal.SIG_IGN:
            signal.signal(signum, _stop_requested)
    
    # Handle color disable
    if args.no_color:
        Colors.disable()
    
    C = Colors
    
    # Validate: require either -d or --single
    if not args.directory and not args.single:
        parser.error("either -d/--directory or --single is required")
    
    # Build list of mov files to process
    if args.single:
        # --single mode: process specific files
        mov_files = []
        for f in args.single:
            p = Path(f).resolve()  # Get absolute path
            if not p.exists():
                print_status("error", f"File not found: {p}")
                sys.exit(EXIT_FAILED)
            if not p.is_file():
                print_status("error", f"Not a file: {p}")
                sys.exit(EXIT_FAILED)
            if not p.suffix.lower() == '.mov':
                print_status("error", f"Not a .mov file: {p}")
                sys.exit(EXIT_FAILED)
            mov_files.append(p)
        
        # Find common parent directory for base path display
        if len(mov_files) == 1:
            base_path = mov_files[0].parent
        else:
            # Find common ancestor using os.path.commonpath
            try:
                base_path = Path(os.path.commonpath([str(f) for f in mov_files]))
            except ValueError:
                # No common path (e.g., different drives on Windows)
                base_path = mov_files[0].parent
        
        mode_desc = f"Processing {len(mov_files)} specified file(s)"
    else:
        # -d mode: process all .mov files in directory
        input_dir = Path(args.directory).resolve()  # Get absolute path
        
        if not input_dir.exists():
            print_status("error", f"Directory not found: {input_dir}")
            sys.exit(EXIT_FAILED)
        
        if not input_dir.is_dir():
            print_status("error", f"Not a directory: {input_dir}")
            sys.exit(EXIT_FAILED)
        
        # Case-insensitive glob for .mov files
        mov_files = sorted([
            f for f in input_dir.iterdir()
            if f.is_file() and f.suffix.lower() == '.mov'
        ])
        base_path = input_dir
        mode_desc = f"Directory mode"
    
    # Print header
    print(f"\n{C.BOLD}{C.CYAN}{'─' * 60}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}  MOV to MKV Conversion{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}{'─' * 60}{C.RESET}")
    print(f"  {mode_desc}")
    print(f"  Base path: {C.WHITE}{base_path}{C.RESET}")
    if args.dry_run:
        print(f"  {C.YELLOW}{C.BOLD}DRY RUN{C.RESET}")
    if args.no_access:
        print(f"  {C.DIM}Skipping access derivatives{C.RESET}")
    if args.overwrite_all:
        print(f"  {C.YELLOW}Overwrite: all outputs{C.RESET}")
    elif args.overwrite:
        print(f"  {C.YELLOW}Overwrite: .mkv and .log only (existing access derivatives are kept){C.RESET}")
    else:
        print(f"  {C.DIM}Existing outputs are never replaced: those files are skipped{C.RESET}")
    if args.progress:
        print(f"  {C.DIM}Progress output enabled{C.RESET}")

    try:
        # Check FFmpeg version (a dry run never runs ffmpeg): -apply_cropping needs 7.1+
        if not args.dry_run:
            version = check_ffmpeg_version()
            if version is None:
                print_status("error", "ffmpeg not found. Please install ffmpeg. Nothing was converted.")
                finish(EXIT_FAILED)
            if version and tuple(int(n) for n in version.split(".")) < (7, 1):
                print_status("error", f"FFmpeg {version} found: this script needs FFmpeg 7.1 or "
                                      f"later (-apply_cropping). Nothing was converted.")
                finish(EXIT_FAILED)
            if not version:
                print_status("warning", "Could not read the FFmpeg version; FFmpeg 7.1 or later "
                                        "is needed (-apply_cropping)")

        # Start timing
        start_time = time.time()

        # Run conversion
        counts = convert_files(mov_files, dry_run=args.dry_run, no_access=args.no_access,
                               overwrite=args.overwrite, overwrite_all=args.overwrite_all,
                               show_progress=args.progress)

        # Show total elapsed time
        elapsed = time.time() - start_time
        hours, remainder = divmod(int(elapsed), 3600)
        minutes, seconds = divmod(remainder, 60)
        print(f"  {C.BOLD}Total time:{C.RESET} {hours:02d}:{minutes:02d}:{seconds:02d}\n")
    except KeyboardInterrupt as e:
        # outside a conversion (between files, or while a log was written)
        print_status("error", f"Interrupted ({stop_reason(e)})")
        finish(interrupt_status(e))
    finish(exit_status(counts))


if __name__ == "__main__":
    main()
