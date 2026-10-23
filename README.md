# JPC AV Scripts

This repository contains three scripts: two Bash scripts (`begin_the_day.sh` and `end_the_day.sh`) for tracking daily activities, and one Python script (`mkv_tag_extractor.py`) for extracting metadata from `.mkv` files. It also has `mov_to_mkv_ffv1.py`, a MOV to FFV1/MKV converter - see [MOV to MKV Converter](#mov-to-mkv-converter).

## Table of Contents
1. [Begin and End The Day Scripts](#begin-and-end-the-day-scripts)
2. [MKV Tag Extractor Script](#mkv-tag-extractor-script)
3. [MOV to MKV Converter](#mov-to-mkv-converter)

---

## Begin and End The Day Scripts

These two Bash scripts help track your day by collecting relevant information, one at the start and one at the end.

### 1. **Begin The Day (`begin_the_day.sh`)**
- Creates a folder named `JPC_AV_YYYYMMDD` in the user's home directory.
- Collects the user's name and thoughts about the day ahead using a graphical dialog.
- Saves the collected information in both `.json` and `.txt` formats.

### 2. **End The Day (`end_the_day.sh`)**
- Similar to `begin_the_day.sh`, but collects reflections on the work completed during the day.
- Saves the collected information in `.json` and `.txt` formats.

### Features:
- **Both scripts**:
  - Check for existing folders and provide feedback.
  - Use `dialog` for user input and `jq` for parsing JSON.
  - Display color-coded success/error messages.

---

## MKV Tag Extractor Script

The `mkv_tag_extractor.py` script extracts metadata from `.mkv` files using `ffprobe`. It processes files in a given directory (and subdirectories) and saves the extracted metadata in both `.json` and `.txt` formats.

### Features:
- Extracts metadata from `.mkv` files using `ffprobe`.
- Saves metadata in both **JSON** and **TXT** formats.
- Warns when output files exist and will be overwritten.
- Processes `.mkv` files in directories and subdirectories.
- Outputs messages with color coding for clarity.

### Prerequisites:
- **colorama**: Install via `pip install colorama` for terminal color output.
- **ffprobe**: Install as part of FFmpeg:
  - **macOS**: `brew install ffmpeg`
  - **Linux**: `sudo apt-get install ffmpeg`
  - **Windows**: Download FFmpeg from [FFmpeg.org](https://ffmpeg.org/download.html).

### Installation:
1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/jpc-av-scripts.git
   cd jpc-av-scripts
   ```

2. Install required dependencies:
   - **For MKV Tag Extractor**:
     ```bash
     pip install colorama
     ```
   
   - **For Bash Scripts**:
     Ensure `zsh`, `dialog`, and `jq` are installed.

### Usage:

#### Bash Scripts:
- **Begin The Day**:
   ```bash
   ./begin_the_day.sh
   ```
- **End The Day**:
   ```bash
   ./end_the_day.sh
   ```

#### MKV Tag Extractor:
Run the Python script with the directory path:
```bash
python3 mkv_tag_extractor.py /path/to/your/directory
```

---

## Output

### Bash Scripts:
Both scripts save the collected data in:
- **JSON**: Structured metadata.
- **TXT**: Plain-text file with the same data.

### MKV Tag Extractor:
- **JSON**: Contains metadata like `ENCODER`, `DESCRIPTION`, etc.
- **TXT**: Structured plain-text metadata, including tags such as `ENCODER`, `AUDIO_STREAM_HASH`, `DESCRIPTION`, etc.

#### Example Output for MKV files:

**JSON Output:**
```json
{
  "file": "JPC_AV_01563.mkv",
  "tags": {
    "ENCODER": "Lavf59.27.100",
    "DESCRIPTION": "Recap of Thirteenth Annual Black Achievement Awards.",
    "TERMS_OF_USE": "Subject to copyright."
  }
}
```

**TXT Output:**
```
file: JPC_AV_01563.mkv
ENCODER: Lavf59.27.100
DESCRIPTION: Recap of Thirteenth Annual Black Achievement Awards.
TERMS_OF_USE: Subject to copyright.
```

---

## Customization
You can customize the scripts by editing:
- **Dialog text** and options for the Bash scripts.
- **Output file paths** and names.


---

## MOV to MKV Converter

`mov_to_mkv_ffv1.py` converts v210 `.mov` transfers into an FFV1/MKV preservation file, an H.264/MP4 access derivative and a conversion log for each file. It is used rarely: read this section before each use.

### Before using it on a real batch

The encoding settings below are those of the last committed version. They were kept, not re-validated. Before the next real use, review the commands and settings against that batch, then convert one representative file and validate the result (for example, compare it with its source and check it against the MediaConch or other preservation policy in use) before converting the rest. Nothing here certifies the tool for arbitrary MOV files.

The tests in `tests/` use synthetic placeholder files and a fake `ffmpeg`. They check the script's decisions, messages, logs and exit statuses only; they do not establish media fidelity, FFmpeg compatibility or preservation-policy compliance.

### Requirements and input assumptions

- Python 3.9 or later (standard library only), and FFmpeg 7.1 or later on `PATH`. `-apply_cropping` needs FFmpeg 7.1, so the script refuses an older FFmpeg before converting anything (if it cannot read the version, it warns and goes on).
- Intended input: NTSC SD v210 `.mov` files - 720x486, interlaced, bottom field first, with at least one audio stream. The script checks none of this. The field-order and interlacing settings are applied regardless, so other material would be mislabelled, and a file without audio fails.
- `-d PATH` takes every file in `PATH` whose name ends in `.mov`, in any letter case (not subfolders). `--single FILE ...` takes the named `.mov` files.

### Outputs

For `/batch/JPC_AV_00001.mov` the script writes, beside it:

```
/batch/JPC_AV_00001/
├── JPC_AV_00001.mkv              FFV1/FLAC preservation file
├── JPC_AV_00001_access.mp4       H.264/AAC access derivative (not with --no-access)
└── JPC_AV_00001_conversion.log   the commands, FFmpeg's output and the result
```

The source `.mov` is never moved, changed or deleted.

### Encoding settings (retained)

Preservation file:

```
ffmpeg -apply_cropping 0 -i SOURCE.mov -map 0:v -map 0:a -c:v ffv1 -level 3 -coder 1
  -context 1 -g 1 -slicecrc 1 -slices 24 -vf setfield=bff -top 0 -flags +ilme+ildct
  -vtag FFV1 -metadata creation_time=<UTC start time> -c:a flac -f matroska -n|-y OUTPUT.mkv
```

Access derivative:

```
ffmpeg -apply_cropping 0 -i SOURCE.mov -map 0:v -map 0:a -c:v libx264 -preset fast -crf 28
  -c:a aac -b:a 128k -movflags +faststart -n|-y OUTPUT_access.mp4
```

- `-apply_cropping 0` keeps the full 720x486 frame (FFmpeg 7.1 and later would otherwise crop to the clean aperture, 704x480).
- `-map 0:v -map 0:a` keeps every video and audio stream and nothing else: timecode, data, subtitle and caption tracks are dropped.
- `setfield=bff`, `-top 0` and `-flags +ilme+ildct` mark and encode the video as interlaced, bottom field first.
- **Metadata change:** `creation_time` is the concrete UTC time the conversion started (for example `2026-10-23T14:05:09.000000Z`), so it also appears in the logged command. The earlier committed version passed the word `now` for FFmpeg to fill in.

### Existing outputs and overwriting

| Options | `.mkv` | Conversion log | Access `.mp4` |
|---|---|---|---|
| none | never replaced | never replaced | never replaced |
| `--overwrite` | replaced | replaced | an existing one is kept as it is - not remade, checked or validated; a missing one is made |
| `--overwrite-all` | replaced | replaced | replaced |
| `--no-access` (with any of the above) | as above | as above | not planned, looked at or made |

Without an overwrite option, a `.mov` with any of its outputs already there is skipped before conversion, and the screen names the files in the way.

In every mode, a `.mov` is also skipped when its output folder or one of its outputs is a symbolic link (nothing is written through a link), and when an earlier input in the same run has the same output folder (the same file named twice, or `X.mov` and `X.MOV`). To be safe, folder names that differ only in letter case count as the same folder, even on a case-sensitive volume.

Replacing starts when FFmpeg starts. The old file cannot be recovered afterwards, and a failed or interrupted replacement leaves an incomplete file in its place.

### Dry runs

`--dry-run` (`-n`) makes the same decisions, and gives the same counts, as a real run with the same options: which files would be converted or skipped, which outputs created or replaced, and which access derivatives kept. It creates no folder or file and does not run `ffmpeg` at all.

### Progress, interruption and partial outputs

- `--progress` shows FFmpeg's progress on standard error. If that output fails (for example, a closed pipe), the running `ffmpeg` is stopped and waited for, and the run stops.
- Ctrl-C normally stops the running `ffmpeg` too, with or without `--progress`, and so do SIGTERM and SIGHUP sent to the script. That file's log then records `INTERRUPTED`, and no further files are started. A run started under `nohup` still ignores SIGHUP. See the known limit below.
- **Known limit - an interruption while `ffmpeg` is starting:** a Ctrl-C, SIGTERM or SIGHUP that arrives while the script is still starting `ffmpeg` for a file can escape this clean-up. That `ffmpeg` may keep running after the script has stopped, and the file's log may not say `INTERRUPTED` (it may still say `IN PROGRESS`). After such an interruption, identify the `ffmpeg` process that belongs to this conversion by its PID and full command, including this file's source and output paths - a list of process names alone does not show which conversion a process belongs to. Stop only that process, and leave unrelated capture or encoding jobs running. If you cannot identify it confidently, ask for help before stopping anything. Treat this conversion's outputs as incomplete before retrying.
- If standard output fails (a closed pipe or terminal, a full disk), the file in progress is finished and logged, no further file is started, and the run exits 1.
- `ffmpeg` gets no keyboard input, so a stray key (FFmpeg stops early on `q`) cannot cut a conversion short.
- Each file's log is written as `IN PROGRESS` before `ffmpeg` starts and rewritten with the result at the end. A log that still says `IN PROGRESS` means the run was stopped before it could record the result (for example, killed outright or a power loss); treat that output as incomplete.
- A failed or interrupted conversion leaves its output incomplete. It is never deleted and never reported complete, and its log says `FAILED` or `INTERRUPTED`. Because that output exists, a later run without an overwrite option skips the `.mov`: read its log, then rerun it with `--overwrite` - or with `--overwrite-all` if its access step failed or was interrupted, since `--overwrite` keeps an existing access `.mp4` as it is.
- The script deletes nothing.

### Exit status

| Status | Meaning |
|---|---|
| 0 | every file converted or skipped (skips are not failures); a dry run finished |
| 1 | a conversion failed, an output folder or log could not be written, the screen or progress output failed, `ffmpeg` is missing or older than 7.1, or a named file or folder was not found |
| 2 | the command line was refused |
| 130 | interrupted with Ctrl-C: the file in progress is incomplete, and later files were not started |
| 143, 129 | stopped by SIGTERM or SIGHUP, the same way as Ctrl-C |

### Examples

```bash
python3 mov_to_mkv_ffv1.py -d /path/to/batch --dry-run
python3 mov_to_mkv_ffv1.py -d /path/to/batch
python3 mov_to_mkv_ffv1.py --single /path/to/JPC_AV_00001.mov --overwrite
```

`python3 mov_to_mkv_ffv1.py --help` describes the same options.

### Tests

```bash
python3 tests/test_mov_to_mkv_ffv1.py
```

Synthetic files and a fake `ffmpeg` only - see the limits above.


---

## Acknowledgments
- [dialog](https://invisible-island.net/dialog/) for the graphical interface.
- [jq](https://stedolan.github.io/jq/) for JSON parsing.
- [colorama](https://pypi.org/project/colorama/) for terminal color support.
