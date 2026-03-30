#!/bin/bash
TARGET="${1:-$AXS_TARGET}"
if [ -z "$TARGET" ]; then
    echo "No target provided" >&2
    exit 1
fi
curl -s "http://$TARGET" | grep -oE 'href="([^"]+)"' | sed 's/href="//;s/"//' | while read link; do
    if [[ "$link" == http* ]]; then
        echo "$link"
    else
        echo "http://$TARGET$link"
    fi
done