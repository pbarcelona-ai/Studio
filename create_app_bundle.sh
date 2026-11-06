#!/usr/bin/env bash
# Create a macOS .app bundle for the Pistachio's Studio
# This creates a clickable app in /Applications

APP_NAME="Pistachio's Studio"
APP_PATH="/Applications/${APP_NAME}.app"
SCRIPT_PATH="/Users/paulbarcelona/Downloads/Studio/run_studio.sh"

echo "Creating ${APP_NAME}.app in /Applications..."

# Create the .app bundle structure
mkdir -p "${APP_PATH}/Contents/MacOS"
mkdir -p "${APP_PATH}/Contents/Resources"

# Create the Info.plist
cat > "${APP_PATH}/Contents/Info.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>run_studio</string>
    <key>CFBundleIdentifier</key>
    <string>com.pistachiosstudio.app</string>
    <key>CFBundleIconFile</key>
    <string>icon</string>
    <key>CFBundleName</key>
    <string>${APP_NAME}</string>
    <key>CFBundleDisplayName</key>
    <string>${APP_NAME}</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.15</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
EOF

# Create the executable wrapper script
cat > "${APP_PATH}/Contents/MacOS/run_studio" << 'EOF'
#!/usr/bin/env bash
# Launcher for Pistachio's Studio - runs the studio server and opens browser

SCRIPT_PATH="/Users/paulbarcelona/Downloads/Studio/run_studio.sh"

# Run the studio script
exec "$SCRIPT_PATH"
EOF

chmod +x "${APP_PATH}/Contents/MacOS/run_studio"

# The icon (a lime P and a coral S that touch) is drawn by scripts/make_icon.py
python3 "$(dirname "$SCRIPT_PATH")/scripts/make_icon.py" "$(mktemp -d)" | sed -n 's/^wrote //p' | grep '\.icns$' | while read -r f; do
  cp "$f" "${APP_PATH}/Contents/Resources/icon.icns"
done
touch "${APP_PATH}"
echo "Created ${APP_PATH}"
echo ""
echo "You can now launch Pistachio's Studio from Applications folder or Spotlight!"

EOF