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
from pathlib import Path
from datetime import datetime

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


# ==============================
# LOGGING
# ==============================

class ConversionLog:
    """Handles per-file logging for conversion process."""
    
    def __init__(self, log_path: Path, source_file: Path):
        self.log_path = log_path
        self.source_file = source_file
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
    
    def log_result(self, success: bool, output_file: Path = None, error_msg: str = None):
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
    
    def finalize(self, overall_success: bool):
        """Add footer and write log to disk."""
        end_time = datetime.now()
        elapsed = end_time - self.start_time
        
        self.lines.append("=" * 70)
        self.lines.append("Summary")
        self.lines.append("=" * 70)
        self.lines.append("")
        self.lines.append(f"Completed:    {end_time.isoformat()}")
        self.lines.append(f"Elapsed:      {elapsed}")
        self.lines.append(f"Status:       {'SUCCESS' if overall_success else 'FAILED'}")
        self.lines.append("")
        
        # Write to file
        with open(self.log_path, 'w') as f:
            f.write('\n'.join(self.lines))

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

{C.BOLD}{C.WHITE}USAGE{C.RESET}
    {C.GREEN}${C.RESET} python3 mov_to_mkv_ffv1.py [-d PATH | --single FILE [FILE ...]] [options]

{C.BOLD}{C.WHITE}OPTIONS{C.RESET}
    {C.CYAN}-d, --directory PATH{C.RESET}       Directory containing .mov files
    {C.CYAN}--single FILE [FILE ...]{C.RESET}   Process specific .mov file(s) directly
    {C.CYAN}-n, --dry-run{C.RESET}              Preview changes without converting
    {C.CYAN}--no-access{C.RESET}                Skip H.264/MP4 access derivative
    {C.CYAN}--no-color{C.RESET}                 Disable colored output

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
    {C.DIM}•{C.RESET} Uses {C.CYAN}-apply_cropping 0{C.RESET} to preserve full frame (720x486)
    {C.DIM}•{C.RESET} FFV1 settings: level 3, slicecrc 1, 24 slices (archival best practice)
    {C.DIM}•{C.RESET} Access derivative: CRF 28, fast preset (optimized for remote viewing)
    {C.DIM}•{C.RESET} Original .mov files are preserved (not moved or deleted)
"""
    return help_text


def get_short_usage():
    """Generate short usage for error messages."""
    C = Colors
    
    usage = f"""
usage: mov_to_mkv_ffv1.py [-d PATH | --single FILE [FILE ...]] [options]
       {C.DIM}Use -h or --help for detailed information{C.RESET}

  {C.CYAN}-d, --directory PATH{C.RESET}       Directory containing .mov files
  {C.CYAN}--single FILE [FILE ...]{C.RESET}   Process specific .mov file(s) directly
  {C.CYAN}-n, --dry-run{C.RESET}              Preview changes without converting
  {C.CYAN}--no-access{C.RESET}                Skip H.264/MP4 access derivative
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


def convert_files(mov_files: list, dry_run: bool = False, no_access: bool = False):
    """Convert .mov files to ffv1/mkv, placing outputs in named subdirectories."""
    C = Colors
    
    if not mov_files:
        print_status("warning", "No .mov files to process")
        return
    
    print(f"\n{C.BOLD}Found {len(mov_files)} .mov file(s) to convert{C.RESET}\n")
    print(f"{C.DIM}{'─' * 60}{C.RESET}")
    
    success_count = 0
    error_count = 0
    
    for i, mov_file in enumerate(mov_files, 1):
        base_name = mov_file.stem  # e.g., "JPC_AV_00013"
        output_dir = mov_file.parent / base_name
        output_file = output_dir / f"{base_name}.mkv"
        access_file = output_dir / f"{base_name}_access.mp4"
        log_file = output_dir / f"{base_name}_conversion.log"
        
        print(f"\n{C.BOLD}[{i}/{len(mov_files)}]{C.RESET} {C.CYAN}{mov_file.name}{C.RESET}")
        print(f"       {C.DIM}→{C.RESET} {output_dir.name}/{output_file.name}")
        if not no_access:
            print(f"       {C.DIM}→{C.RESET} {output_dir.name}/{access_file.name}")
        print(f"       {C.DIM}→{C.RESET} {output_dir.name}/{log_file.name}")
        
        if dry_run:
            print_status("skip", "Skipped (dry run)", indent=3)
            continue
        
        # Create output directory
        output_dir.mkdir(exist_ok=True)
        
        # Initialize per-file log
        log = ConversionLog(log_file, mov_file)
        overall_success = True
        
        # FFV1/MKV preservation file
        # -apply_cropping 0: Prevents FFmpeg 7.1+ from applying clap atom cropping
        #                   (preserves full 720x486 frame instead of cropping to 704x480)
        # -map 0:v -map 0:a: Maps only video and audio streams
        #                    (excludes timecode/tmcd data streams which MKV doesn't support)
        ffv1_cmd = [
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
            "-c:a", "flac",
            "-f", "matroska",
            "-n",
            str(output_file)
        ]
        
        log.log_command("FFV1/MKV Preservation Copy", ffv1_cmd)
        
        try:
            result = subprocess.run(ffv1_cmd, capture_output=True, text=True)
            log.log_output(result.stdout, result.stderr)
            
            if result.returncode == 0:
                log.log_result(True, output_file)
                print_status("success", "FFV1/MKV complete", indent=3)
            else:
                log.log_result(False, error_msg=f"ffmpeg returned {result.returncode}")
                print_status("error", f"FFV1 error: ffmpeg returned {result.returncode}", indent=3)
                overall_success = False
                error_count += 1
                log.finalize(overall_success)
                continue
                
        except FileNotFoundError:
            log.log_result(False, error_msg="ffmpeg not found")
            log.finalize(False)
            print_status("error", "ffmpeg not found. Please install ffmpeg.")
            sys.exit(1)
        
        # H.264/MP4 access derivative (unless --no-access)
        if not no_access:
            access_cmd = [
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
                "-n",
                str(access_file)
            ]
            
            log.log_command("H.264/MP4 Access Derivative", access_cmd)
            
            try:
                result = subprocess.run(access_cmd, capture_output=True, text=True)
                log.log_output(result.stdout, result.stderr)
                
                if result.returncode == 0:
                    log.log_result(True, access_file)
                    print_status("success", "H.264/MP4 access complete", indent=3)
                else:
                    log.log_result(False, error_msg=f"ffmpeg returned {result.returncode}")
                    print_status("error", f"Access error: ffmpeg returned {result.returncode}", indent=3)
                    overall_success = False
                    error_count += 1
                    log.finalize(overall_success)
                    continue
                    
            except FileNotFoundError:
                log.log_result(False, error_msg="ffmpeg not found")
                log.finalize(False)
                print_status("error", "ffmpeg not found. Please install ffmpeg.")
                sys.exit(1)
        
        # Finalize log
        log.finalize(overall_success)
        print_status("success", f"Log saved: {log_file.name}", indent=3)
        success_count += 1
    
    # Summary
    print(f"\n{C.DIM}{'─' * 60}{C.RESET}")
    print(f"\n{C.BOLD}SUMMARY{C.RESET}")
    if dry_run:
        print(f"  {C.YELLOW}DRY RUN - No files were converted{C.RESET}")
    else:
        print(f"  {C.GREEN}Converted:{C.RESET} {success_count}")
        if error_count > 0:
            print(f"  {C.RED}Errors:{C.RESET}    {error_count}")
    print()


# ==============================
# MAIN
# ==============================

def main():
    """Main execution function."""
    
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
        '--no-color',
        action='store_true',
        help=argparse.SUPPRESS
    )
    
    args = parser.parse_args()
    
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
            p = Path(f)
            if not p.exists():
                print_status("error", f"File not found: {p}")
                sys.exit(1)
            if not p.suffix.lower() == '.mov':
                print_status("error", f"Not a .mov file: {p}")
                sys.exit(1)
            mov_files.append(p)
        mode_desc = f"Processing {len(mov_files)} specified file(s)"
    else:
        # -d mode: process all .mov files in directory
        input_dir = Path(args.directory)
        
        if not input_dir.exists():
            print_status("error", f"Directory not found: {input_dir}")
            sys.exit(1)
        
        if not input_dir.is_dir():
            print_status("error", f"Not a directory: {input_dir}")
            sys.exit(1)
        
        mov_files = sorted(input_dir.glob("*.mov"))
        mode_desc = f"Directory: {input_dir}"
    
    # Print header
    print(f"\n{C.BOLD}{C.CYAN}{'─' * 60}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}  MOV to MKV Conversion{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}{'─' * 60}{C.RESET}")
    print(f"  {mode_desc}")
    if args.dry_run:
        print(f"  {C.YELLOW}{C.BOLD}DRY RUN{C.RESET}")
    if args.no_access:
        print(f"  {C.DIM}Skipping access derivatives{C.RESET}")
    
    # Start timing
    start_time = time.time()
    
    # Run conversion
    convert_files(mov_files, dry_run=args.dry_run, no_access=args.no_access)
    
    # Show elapsed time
    elapsed = time.time() - start_time
    hours, remainder = divmod(int(elapsed), 3600)
    minutes, seconds = divmod(remainder, 60)
    print(f"  {C.DIM}Elapsed: {hours:02d}:{minutes:02d}:{seconds:02d}{C.RESET}\n")


if __name__ == "__main__":
    main()