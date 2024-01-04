#!/bin/zsh

# Function to begin the day and collect information
btd() {
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
  DIALOG_CMD="dialog --json --ontop --big --background color=#169122 --title 'JPC AV: Begin The Day' --message 'As you begin the day, please provide your name and describe your thoughts on the day ahead of you.' --textfield 'Begin The Day Thoughts,editor' --selecttitle 'Name' --selectvalues 'David Sohl, Bleakley McDowell' --selectdefault 'David Sohl' --buttonstyle center --button1text 'ONWARD!!' --button2text 'Cancel'"
  
  # Execute the DIALOG_CMD and capture its output in a variable
  USER_INPUT=$(eval "$DIALOG_CMD")
  
  # Extract the user input from the JSON output
  USER_THOUGHTS=$(echo "$USER_INPUT" | jq -r '."Begin The Day Thoughts"')
  USER_NAME=$(echo "$USER_INPUT" | jq -r '.Name.selectedValue')
  
  # Check if the user canceled the dialog or closed it
  if [ -z "$USER_THOUGHTS" ]; then
    # Information collection canceled
    echo -e "\n${RED}${BOLD}Information collection canceled.${NC}"
    exit 1
  fi
  
  # Create a JSON object with the collected information
  JSON_DATA="{\"Name\": \"$USER_NAME\", \"Begin The Day Thoughts\": \"$USER_THOUGHTS\"}"
  
  # Save the user input as JSON formatted text data to the JSON file using a here document
  cat <<EOF >> "$HOME_DIR/$FOLDER_NAME/$JSON_FILE_NAME"
### $FOLDER_NAME ###

*** BEGIN THE DAY ***

$JSON_DATA

EOF

  # Save the user input as unformatted text to the TXT file using a here document
  cat <<EOF >> "$HOME_DIR/$FOLDER_NAME/$TXT_FILE_NAME"
### $FOLDER_NAME ###

*** BEGIN THE DAY ***

NAME: "$USER_NAME"

Begin The Day Thoughts: "$USER_THOUGHTS"

EOF

  # Provide a message indicating successful information saving
  echo ""
  echo -e "\n${GREEN}${BOLD}Begin The Day information saved to $HOME_DIR/$FOLDER_NAME/ THANK YOU!!${NC}"
}

# Call the "begin" function to begin the day and collect information
btd