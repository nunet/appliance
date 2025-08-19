#!/bin/bash

# Path to the EFF wordlist
WORDLIST="$HOME/menu/scripts/eff_large_wordlist.txt"

# Function to get a random word from the wordlist
get_random_word() {
    # Get a random line number between 1 and the total number of lines
    total_lines=$(wc -l < "$WORDLIST")
    random_line=$((RANDOM % total_lines + 1))
    
    # Get the word from that line (second column)
    word=$(sed -n "${random_line}p" "$WORDLIST" | cut -f2)
    echo "$word"
}

# Generate a code using a random number and two random words
generate_code() {
    # Generate random number between 1 and 999  
    number=$((RANDOM % 999 + 1))
    
    # Get two random words
    word1=$(get_random_word)
    word2=$(get_random_word)
    
    # Format: number-word1-word2
    echo "${number}-${word1}-${word2}"
}

# Generate and output the code
generate_code 