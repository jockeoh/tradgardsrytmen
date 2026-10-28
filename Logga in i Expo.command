#!/bin/zsh
cd -- "${0:A:h}/mobile"
unset EXPO_OFFLINE
export EXPO_NO_TELEMETRY=1
node node_modules/expo/bin/cli login --username jockeoh
printf '\nTryck Retur för att stänga.\n'
read
