#!/bin/zsh

# Function to end the day and collect information
etd() {
  # Define ANSI escape codes for text colors and styles
  GREEN='\033[0;32m'    # Sets text color to green
  RED='\033[0;31m'      # Sets text color to red
  ORANGE='\033[38;5;208m'  # Sets text color to orange
  NC='\033[0m'          # Resets text color to default (No Color)
  BOLD='\033[1m'        # Makes text bold
  NORMAL='\033[0m'      # Resets text style to normal

  # Define the path to the home directory
  HOME_DIR="/Users/$(whoami)"
  
  # Get the current date in the format YYYYMMDD
  DATE=$(date +"%Y%m%d")
  
  # Create the folder name
  FOLDER_NAME="JPC_AV_$DATE"

  # Check if the folder already exists
  if [ -d "$HOME_DIR/$FOLDER_NAME" ]; then
    # Folder already exists, provide a message
    echo ""
    echo -e "${ORANGE}Folder '$FOLDER_NAME' already exists. Not a problem!${NC}"
  else
    # Create the folder in the home directory
    if mkdir -p "$HOME_DIR/$FOLDER_NAME"; then
      # Folder created successfully
      echo ""
      echo -e "${GREEN}${BOLD}Folder '$FOLDER_NAME' created successfully.${NC}"
    else
      # Error message for folder creation failure
      echo ""
      echo -e "${RED}${BOLD}Failed to create folder.${NC}"
      exit 1
    fi
  fi

  # Continue with the rest of the script

  # Create the JSON file name
  JSON_FILE_NAME="$FOLDER_NAME.json"
  
  # Create the TXT file name
  TXT_FILE_NAME="$FOLDER_NAME.txt"

  # Define the `swiftDialog` command for creating a graphical dialog
  DIALOG_CMD="dialog --json --ontop --big --background color=#431c53 --title 'JPC AV: End The Day' --message 'As you end the day, please provide information on the work completed and describe your thoughts on how the day went.' --textfield 'End The Day Thoughts,editor' --selecttitle 'Format Digitized' --selectvalues 'One-inch videotape, U-matic, Betacam, VHS' --selectdefault 'One-inch videotape' --selecttitle 'Number of Format Digitized' --selectvalues $(seq -s ',' 0 20) --selectdefault '0' --buttonstyle center --button1text 'See you next time!!' --button2text 'Cancel'"

  # Execute the DIALOG_CMD and capture its output in a variable
  USER_INPUT=$(eval "$DIALOG_CMD")

  # Extract the user input from the JSON output
  USER_THOUGHTS=$(jq -r '."End The Day Thoughts"' <<< "$USER_INPUT")
  FORMAT_DIGITIZED=$(jq -r '."Format Digitized".selectedValue' <<< "$USER_INPUT")
  NUMBER_DIGITIZED=$(jq -r '."Number of Format Digitized".selectedValue' <<< "$USER_INPUT")

  # Check if the user canceled the dialog or closed it
  if [ -z "$USER_THOUGHTS" ]; then
    # Information collection canceled
    echo ""
    echo -e "${RED}${BOLD}Information collection canceled.${NC}"
    exit 1
  fi

  # Create a JSON object with the collected information
  JSON_DATA="{\"End The Day Thoughts\": \"$USER_THOUGHTS\", \"Format Digitized\": \"$FORMAT_DIGITIZED\", \"Number of Format Digitized\": \"$NUMBER_DIGITIZED\"}"

  # Save the JSON data to the JSON file using a here document
  cat <<EOF >> "$HOME_DIR/$FOLDER_NAME/$JSON_FILE_NAME"

---------------------------------------------
---------------------------------------------

*** END THE DAY ***

$JSON_DATA

EOF

  # Save the same JSON data to the TXT file using a here document
  cat <<EOF >> "$HOME_DIR/$FOLDER_NAME/$TXT_FILE_NAME"

---------------------------------------------
---------------------------------------------

*** END THE DAY ***

End The Day Thoughts: "$USER_THOUGHTS"

Format Digitized: "$FORMAT_DIGITIZED"

Number Digitized: "$NUMBER_DIGITIZED"
EOF

  # Provide a message indicating successful information saving
  echo ""
  echo -e "${GREEN}${BOLD}End The Day information saved to $HOME_DIR/$FOLDER_NAME/ THANK YOU!!${NC}"
}

# Call the "etd" function
etd