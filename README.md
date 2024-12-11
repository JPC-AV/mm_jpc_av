
```markdown
# JPC AV: Begin and End The Day Scripts

This repository contains two Bash scripts designed to help users track their day by collecting relevant information in a structured format. One script, `begin_the_day.sh`, is used at the start of the day to capture initial thoughts, and the other, `end_the_day.sh`, is used at the end of the day to capture reflections on completed work. Both scripts save the collected data in both JSON and plain text formats.

## Features

- **Begin The Day (`begin_the_day.sh`)**:
  - Creates a folder in the user's home directory named `JPC_AV_YYYYMMDD` (where `YYYYMMDD` is the current date).
  - Collects the user's name and thoughts about the day ahead using a graphical dialog interface.
  - Saves the collected information in both `.json` and `.txt` files.

- **End The Day (`end_the_day.sh`)**:
  - Similar to the "Begin The Day" script, this script creates a folder named `JPC_AV_YYYYMMDD`.
  - Collects reflections on the work completed during the day, including thoughts on the work and the formats digitized.
  - Saves the collected data in `.json` and `.txt` files.

Both scripts:
- Check if the folder already exists and provide feedback to the user.
- Provide clear color-coded success or error messages in the terminal using ANSI escape codes.
- Use `dialog` for the graphical interface and `jq` for parsing JSON data.

## Prerequisites

- **zsh**: These scripts are written for `zsh`. Ensure you're using `zsh` as your shell.
- **dialog**: The script uses the `dialog` command to create a graphical interface for user input. Install it using your package manager (e.g., `brew install dialog` on macOS).
- **jq**: `jq` is required to parse JSON data. You can install it via `brew install jq` or `apt-get install jq`.

## Installation

1. Ensure that `zsh`, `dialog`, and `jq` are installed on your system.

2. Clone the repository:

```bash
git clone https://github.com/yourusername/jpc-av-begin-end-the-day.git
cd jpc-av-begin-end-the-day
```

3. Give execution permission to the scripts:

```bash
chmod +x begin_the_day.sh end_the_day.sh
```

## Usage

To use the scripts, simply run them:

- **Begin The Day**:

```bash
./begin_the_day.sh
```

- **End The Day**:

```bash
./end_the_day.sh
```

### What Happens When You Run the Scripts?

1. **Folder Creation**: Both scripts check if a folder named `JPC_AV_YYYYMMDD` exists in the user's home directory. If it doesn't, the folder is created.

2. **Dialog for User Input**:
   - **Begin The Day**: Prompts for your name and thoughts on the day ahead.
   - **End The Day**: Prompts for your reflections on the day, including the formats digitized and the number of formats digitized.

3. **Data Saving**: Both scripts save the collected information in both `.json` and `.txt` formats in the newly created folder.

4. **Confirmation**: A success message is displayed in the terminal to confirm that the data has been saved.

### Example Output

For **Begin The Day**:

```bash
Folder 'JPC_AV_20241211' created successfully.
Name: "David Sohl"
Begin The Day Thoughts: "I'm excited to start working on the digitization project today."
Begin The Day information saved to /Users/username/JPC_AV_20241211/
```

For **End The Day**:

```bash
Folder 'JPC_AV_20241211' created successfully.
End The Day Thoughts: "It was a productive day. I digitized several formats."
Format Digitized: "VHS"
Number Digitized: 5
End The Day information saved to /Users/username/JPC_AV_20241211/
```

## Script Customization

You can customize both scripts by editing the following:

- The title and message in the `dialog` command.
- The selectable options for names, formats, and other fields.
- The file paths and names where the data is saved.

## Acknowledgments

- [dialog](https://invisible-island.net/dialog/) for creating the graphical dialog interface.
- [jq](https://stedolan.github.io/jq/) for JSON parsing.

```

---

# MKV Tag Extractor

## Description

This script is designed to extract metadata, specifically the `tags` section, from `.mkv` files using **ffprobe**. It processes all MKV files in a given directory (and its subdirectories), saving the extracted metadata as both **JSON** and **TXT** files. The script also handles overwriting existing output files and displays clear feedback on the progress.

## Features

- Extracts metadata from `.mkv` files using **ffprobe**.
- Saves the extracted data in **JSON** and **TXT** formats.
- Handles file overwriting with clear warnings.
- Supports batch processing of MKV files in directories and subdirectories.
- Outputs neatly formatted messages with color coding for readability.

## Requirements

### Dependencies

To run this script, you'll need the following Python dependency:

- **colorama**: For colored terminal output.

  Install it using:
  ```bash
  pip install colorama
  ```

### External Tools

- **ffprobe**: This script uses `ffprobe` (part of the **FFmpeg** suite) to extract metadata from `.mkv` files. 

  You can install FFmpeg (which includes ffprobe) as follows:

  - **macOS (Homebrew)**:
    ```bash
    brew install ffmpeg
    ```
  - **Linux (apt)**:
    ```bash
    sudo apt-get install ffmpeg
    ```
  - **Windows**: 
    Download FFmpeg from [https://ffmpeg.org/download.html](https://ffmpeg.org/download.html) and add it to your PATH.

## Usage

### Command Line

To use the script, run the following command in your terminal:

```bash
python3 mkv_tag_extract.py /path/to/your/directory
```

Where `/path/to/your/directory` is the path to the directory containing the `.mkv` files you want to process. The script will:

- Traverse the given directory and its subdirectories.
- Extract metadata from each `.mkv` file.
- Save the metadata in both `.json` and `.txt` files in the same directory as the `.mkv` file.

### Example Output:

```
Found file: JPC_AV_01563.mkv

Warning: /Volumes/JPCARCHIVE/01a_metadataEmbedded/JPC_AV_01563/JPC_AV_01563_output_tags.json exists and will be overwritten.
Warning: /Volumes/JPCARCHIVE/01a_metadataEmbedded/JPC_AV_01563/JPC_AV_01563_output_tags.txt exists and will be overwritten.

Processing: JPC_AV_01563.mkv

Saved (or overwritten): /Volumes/JPCARCHIVE/01a_metadataEmbedded/JPC_AV_01563/JPC_AV_01563_output_tags.json
Saved (or overwritten): /Volumes/JPCARCHIVE/01a_metadataEmbedded/JPC_AV_01563/JPC_AV_01563_output_tags.txt

Completed: JPC_AV_01563.mkv

Moving to next .mkv file
------------------------------------------------------------------------

Found file: JPC_AV_01562.mkv

Warning: /Volumes/JPCARCHIVE/01a_metadataEmbedded/JPC_AV_01562/JPC_AV_01562_output_tags.json exists and will be overwritten.
Warning: /Volumes/JPCARCHIVE/01a_metadataEmbedded/JPC_AV_01562/JPC_AV_01562_output_tags.txt exists and will be overwritten.

Processing: JPC_AV_01562.mkv

Saved (or overwritten): /Volumes/JPCARCHIVE/01a_metadataEmbedded/JPC_AV_01562/JPC_AV_01562_output_tags.json
Saved (or overwritten): /Volumes/JPCARCHIVE/01a_metadataEmbedded/JPC_AV_01562/JPC_AV_01562_output_tags.txt

Completed: JPC_AV_01562.mkv

Moving to next .mkv file
------------------------------------------------------------------------
```

## Output Format

For each `.mkv` file processed:

- **JSON output**: A file in the same directory as the `.mkv` file, containing the metadata in JSON format.
- **TXT output**: A file in the same directory as the `.mkv` file, containing the metadata in a structured plain-text format, including tags such as `ENCODER`, `DESCRIPTION`, `DATE_DIGITIZED`, etc.

The output will look like this:

### Sample JSON Output

```json
{
    "file": "JPC_AV_01563.mkv",
    "tags": {
        "ENCODER": "Lavf59.27.100",
        "VIDEO_STREAM_HASH": "c45b02b4a54974ddf81f46bd5f060a67",
        "AUDIO_STREAM_HASH": "3da21a4be412c7944cf0ebc29aa03592",
        "COLLECTION": "Johnson Publishing Company Archive",
        "DESCRIPTION": "00:01:17 - Recap of Thirteenth Annual Black Achievement Awards.",
        "TERMS_OF_USE": "Some or all of this video may be subject to copyright."
    }
}
```

### Sample TXT Output

```
file: JPC_AV_01563.mkv

ENCODER: Lavf59.27.100

VIDEO_STREAM_HASH: c45b02b4a54974ddf81f46bd5f060a67
AUDIO_STREAM_HASH: 3da21a4be412c7944cf0ebc29aa03592

COLLECTION: Johnson Publishing Company Archive

DESCRIPTION: 00:01:17 - Recap of Thirteenth Annual Black Achievement Awards.

TERMS_OF_USE: Some or all of this video may be subject to copyright.
```
