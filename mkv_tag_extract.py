import json
import subprocess
import os
import argparse
from colorama import init, Fore, Style

# Initialize colorama
init(autoreset=True)

def extract_mkv_metadata(file_path):
    """
    Extracts the 'tags' section from an MKV file using ffprobe and returns it as a dictionary.
    """
    try:
        # Check if the file exists
        if not os.path.isfile(file_path):
            print(f"{Fore.RED}Error: File '{file_path}' does not exist.")
            return None
        
        # Run ffprobe to get the metadata of the MKV file
        process = subprocess.Popen(
            ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', file_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            # If there is an error, print both stdout and stderr for better diagnostics
            print(f"{Fore.RED}Error while extracting metadata from {file_path}:")
            print(f"{Fore.YELLOW}stdout: {stdout.decode()}")
            print(f"{Fore.YELLOW}stderr: {stderr.decode()}")
            return None

        # Parse the JSON output from ffprobe
        metadata = json.loads(stdout.decode())

        # Extract only the "tags" section from the format metadata
        tags = metadata.get('format', {}).get('tags', {})

        # Structure the extracted data in a dictionary format
        structured_data = {
            'file': os.path.basename(file_path),
            'tags': tags
        }

        return structured_data

    except Exception as e:
        # Catch any exceptions, print the error message and traceback for better diagnosis
        print(f"{Fore.RED}Error while extracting metadata from {file_path}: {e}")
        return None

def save_metadata_to_json(data, output_file):
    """
    Saves the extracted tags to a JSON file.
    """
    with open(output_file, 'w') as json_file:
        json.dump(data, json_file, indent=4)
    print(f"{Fore.GREEN}Saved (or overwritten): {output_file}")

def save_metadata_to_txt(data, output_file):
    """
    Saves the extracted tags to a text file in the requested format.
    """
    with open(output_file, 'w') as txt_file:
        txt_file.write(f"file: {data['file']}\n\n")

        # The desired order of tags
        order_of_tags = [
            "ENCODER", "VIDEO_STREAM_HASH", "AUDIO_STREAM_HASH", 
            "COLLECTION", "TITLE", "CATALOG_NUMBER", 
            "DESCRIPTION", "DATE_DIGITIZED", "ENCODER_SETTINGS", 
            "ENCODED_BY", "ORIGINAL_MEDIA_TYPE", "DATE_TAGGED", 
            "TERMS_OF_USE", "_TECHNICAL_NOTES", "_ORIGINAL_FPS"
        ]

        # Iterate over the specified order and write each tag with spacing
        for idx, key in enumerate(order_of_tags):
            if key in data['tags']:
                # Only write AUDIO_STREAM_HASH once
                if key == "VIDEO_STREAM_HASH":
                    txt_file.write(f"{key}: {data['tags'][key]}")
                    if "AUDIO_STREAM_HASH" in data['tags']:
                        txt_file.write(f"\nAUDIO_STREAM_HASH: {data['tags']['AUDIO_STREAM_HASH']}\n\n")
                elif key != "AUDIO_STREAM_HASH":
                    txt_file.write(f"{key}: {data['tags'][key]}\n\n")

    print(f"{Fore.GREEN}Saved (or overwritten): {output_file}\n")

def process_directory(directory):
    """
    Processes all MKV files in the given directory and any subdirectories.
    """
    # Ensure the directory exists
    if not os.path.isdir(directory):
        print(f"{Fore.RED}Error: The directory '{directory}' does not exist.\n")
        return

    # Walk through the directory and its subdirectories
    for root, dirs, files in os.walk(directory):
        for filename in files:
            if filename.endswith('.mkv'):
                file_path = os.path.join(root, filename)

                # Notify that we found the .mkv file
                print(f"\n{Fore.CYAN}Found file: {filename}\n")

                # Extract metadata for each MKV file
                extracted_data = extract_mkv_metadata(file_path)

                if extracted_data:
                    # Create output file names based on the 'file' key
                    base_filename = extracted_data['file'].split('.')[0]  # Remove extension for file name
                    
                    # Create output JSON and TXT file names
                    output_json = os.path.join(root, f"{base_filename}_output_tags.json")
                    output_txt = os.path.join(root, f"{base_filename}_output_tags.txt")

                    # Check if files already exist and overwrite them
                    overwrite_msg = ""
                    if os.path.exists(output_json):
                        overwrite_msg += f"{Fore.YELLOW}Warning: {output_json} exists and will be overwritten.\n"
                    if os.path.exists(output_txt):
                        overwrite_msg += f"{Fore.YELLOW}Warning: {output_txt} exists and will be overwritten.\n"

                    # Print overwrite message with line breaks between warnings
                    if overwrite_msg:
                        print(overwrite_msg.strip())  # Ensure warning messages are printed on separate lines
                        print()  # Adding an extra blank line after the warnings to match the desired output

                    # Print the Processing message first
                    print(f"{Fore.CYAN}Processing: {filename}")

                    # Then save messages are printed
                    save_metadata_to_json(extracted_data, output_json)
                    save_metadata_to_txt(extracted_data, output_txt)

                    # After saving, print the Completed message
                    print(f"{Fore.GREEN}Completed: {filename}")
                    print(f"{Fore.MAGENTA}Moving to next .mkv file\n" + "-"*70 + "\n")
                else:
                    print(f"{Fore.RED}Failed to extract metadata from {filename}.\n")
            else:
                # Skip non-MKV files without much verbosity
                pass

def main():
    # Parse command-line arguments for multiple directories
    parser = argparse.ArgumentParser(description="Extract 'tags' from all MKV files in a directory and subdirectories, saving as JSON and TXT")
    parser.add_argument("directories", help="Paths to directories containing MKV files", nargs='+')

    args = parser.parse_args()

    # Process each directory passed as argument
    for directory in args.directories:
        process_directory(directory)

if __name__ == '__main__':
    main()