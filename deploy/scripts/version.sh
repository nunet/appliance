#!/bin/bash

set -exuo pipefail

# Get the most recent tag (assumes tags are like v1.2.3)
LAST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "v0.0.0")
LAST_VERSION=$(echo $LAST_TAG | sed 's/^v//')

# Parse commits since last tag for version bump
MAJOR=$(git log --oneline $LAST_TAG..HEAD --format=%s | grep -i -c "^BREAKING CHANGE\|MAJOR VERSION" || true)
MINOR=$(git log --oneline $LAST_TAG..HEAD --format=%s | grep -i -c "^feat:" || true)
PATCH=$(git log --oneline $LAST_TAG..HEAD --format=%s | grep -i -c "^fix:" || true)

echo "Last version: $LAST_VERSION"
echo "Commits since last tag: $(git log --oneline $LAST_TAG..HEAD | wc -l)"
echo "Detected bumps - Major: $MAJOR, Minor: $MINOR, Patch: $PATCH"

# Determine bump type (major > minor > patch)
if [ $MAJOR -gt 0 ]; then
    export APPLIANCE_NEW_VERSION=$(echo $LAST_VERSION | awk -F. '{print $1+1,0,0}' OFS=.)
elif [ $MINOR -gt 0 ]; then
    export APPLIANCE_NEW_VERSION=$(echo $LAST_VERSION | awk -F. '{print $1,$2+1,0}' OFS=.)
elif [ $PATCH -gt 0 ]; then
    export APPLIANCE_NEW_VERSION=$(echo $LAST_VERSION | awk -F. '{print $1,$2,$3+1}' OFS=.)
else
    echo "No version bump needed."
    exit 0
fi


# if in CI and if on main or release branch then apply the version bump
echo $GITLAB_CI
echo $CI_COMMIT_REF_NAME
if [[ -n ${GITLAB_CI+x} && ( $CI_COMMIT_REF_NAME =~ ^(main|master|release)$ ) ]]; then
    # Push (uncomment in CI)
    git config --global user.email "ci@nunet.io"
    git config --global user.name "NuNet GitLab CI"
    git tag -a "v$APPLIANCE_NEW_VERSION" -m "v$APPLIANCE_NEW_VERSION"
    git push https://oauth2:"$CI_TAG_PUSH_TOKEN@gitlab.com/$CI_PROJECT_PATH".git --tags

    echo "Bumped to $APPLIANCE_NEW_VERSION"
else
    echo "New version would be: $APPLIANCE_NEW_VERSION"
    echo "Run in CI to apply the version bump."
fi
