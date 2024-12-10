# Scripts for management of JPC AV files
- begin & end
  - these two scripts are meant to be run at the beginning and ending of the day, respectively.
  - they each pop up dialog boxes that collect some basic user information about the day's work.
  - required dependencies:
    - swfitDialog
      - https://github.com/swiftDialog/swiftDialog/releases
      - go with the latest .pkg
      - installs correctly to /usr/local/bin/
    - jq
      - `brew install jq`
     
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

- **Python 3.x**
- **ffprobe** (part of FFmpeg)
- **colorama** (for colored output in the terminal)

### Install ffprobe

If you don't have **ffprobe** installed, you can install FFmpeg, which includes ffprobe:

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

### Install Dependencies

You need to install the `colorama` package. Use pip:

```bash
pip install colorama
```

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

