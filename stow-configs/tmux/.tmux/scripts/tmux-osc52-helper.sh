#!/bin/bash
# tmux OSC 52 clipboard helper
# Reads selection from stdin, base64 encodes it,
# and writes the OSC 52 escape sequence directly to the tmux client TTY

content=$(cat)
if [ -z "$content" ]; then
    exit 0
fi

# Get the client tty from tmux
client_tty=$(tmux display -p '#{client_tty}' 2>/dev/null)
if [ -z "$client_tty" ] || [ ! -c "$client_tty" ]; then
    exit 1
fi

encoded=$(echo -n "$content" | base64 -w0 2>/dev/null || echo -n "$content" | base64)
printf "\033]52;c;%s\a" "$encoded" > "$client_tty"
