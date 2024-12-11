# JPC AV Scripts

This repository contains three scripts: two Bash scripts (`begin_the_day.sh` and `end_the_day.sh`) for tracking daily activities, and one Python script (`mkv_tag_extractor.py`) for extracting metadata from `.mkv` files.

## Table of Contents
1. [Begin and End The Day Scripts](#begin-and-end-the-day-scripts)
2. [MKV Tag Extractor Script](#mkv-tag-extractor-script)

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

## Acknowledgments
- [dialog](https://invisible-island.net/dialog/) for the graphical interface.
- [jq](https://stedolan.github.io/jq/) for JSON parsing.
- [colorama](https://pypi.org/project/colorama/) for terminal color support.
