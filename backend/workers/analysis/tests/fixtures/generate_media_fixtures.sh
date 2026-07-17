#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  printf 'usage: %s OUTPUT_DIRECTORY\n' "$0" >&2
  exit 2
fi

readonly output_directory="$1"
mkdir -p "$output_directory"

ffmpeg -hide_banner -loglevel error -y \
  -f lavfi -i 'testsrc2=size=3840x2160:rate=60:duration=0.20' \
  -f lavfi -i 'sine=frequency=440:sample_rate=48000:duration=0.20' \
  -c:v libx264 -preset ultrafast -pix_fmt yuv420p -c:a aac -shortest \
  "$output_directory/4k60-h264.mp4"

ffmpeg -hide_banner -loglevel error -y \
  -f lavfi -i 'testsrc2=size=960x540:rate=24:duration=0.25' \
  -c:v libx264 -preset ultrafast -pix_fmt yuv420p -an \
  "$output_directory/540p24.mp4"

ffmpeg -hide_banner -loglevel error -y \
  -f lavfi -i 'testsrc2=size=640x360:rate=24:duration=0.25' \
  -c:v libx264 -preset ultrafast -pix_fmt yuv420p -an \
  "$output_directory/rotation-base.mp4"
ffmpeg -hide_banner -loglevel error -y \
  -display_rotation 90 -i "$output_directory/rotation-base.mp4" -c copy \
  "$output_directory/rotated.mov"
rm "$output_directory/rotation-base.mp4"

ffmpeg -hide_banner -loglevel error -y \
  -f lavfi -i 'testsrc2=size=640x360:rate=30:duration=0.20' \
  -c:v libx264 -preset ultrafast -pix_fmt yuv420p -an \
  "$output_directory/no-audio.mp4"

ffmpeg -hide_banner -loglevel error -y \
  -f lavfi -i 'sine=frequency=880:sample_rate=48000:duration=0.20' \
  -c:a aac "$output_directory/audio-only.m4a"

printf 'not a media container\n' > "$output_directory/corrupt.mp4"

# One small frame per second keeps this over-six-minute fixture inexpensive.
ffmpeg -hide_banner -loglevel error -y \
  -f lavfi -i 'color=c=black:size=16x16:rate=1:duration=361' \
  -c:v libx264 -preset ultrafast -pix_fmt yuv420p -an \
  "$output_directory/over-six-minutes.mp4"
