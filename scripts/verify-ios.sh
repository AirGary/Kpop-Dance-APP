#!/usr/bin/env bash
set -euo pipefail

readonly project="kpop.xcodeproj"
readonly destination="${IOS_DESTINATION:-platform=iOS Simulator,name=iPhone 17}"

xcodebuild \
  -project "$project" \
  -scheme kpop \
  -destination "$destination" \
  test

xcodebuild \
  -project "$project" \
  -scheme kpop-Staging \
  -configuration Staging \
  -destination "$destination" \
  build

xcodebuild \
  -project "$project" \
  -scheme kpop \
  -configuration Release \
  -destination 'generic/platform=iOS Simulator' \
  build
