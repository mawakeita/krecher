#!/bin/bash
# Keeps gemma4:e4b loaded on the D12 box during a demo. Stop with Ctrl+C.
URL="http://100.95.113.72:8800/u/d12/api/generate"
while true; do
  if curl -sf -m 30 "$URL" -d '{"model":"gemma4:e4b","keep_alive":"30m"}' > /dev/null; then
    echo "$(date +%H:%M) warm"
  else
    echo "$(date +%H:%M) NO ANSWER: check your lease"
  fi
  sleep 1200
done
