#!/usr/bin/env bash
# Create "Pistachio's Studio.app" in /Applications: a normal double-clickable app with no Terminal window.
# Opening it starts the Studio server in the background and opens your browser; it stays in the Dock, and Quit (Cmd-Q) stops the server.
# Clicking its Dock icon again re-opens the browser tab. The server's output goes to ~/Library/Logs/Pistachios Studio.log.
# It runs the Studio's own .venv Python (made by install.sh) when there is one, else python3, through an interactive zsh, so it sees the same environment as Terminal.
# Built with osacompile (a standard AppleScript app, which macOS starts reliably). If the app is force-quit the server keeps running; stop it with: pkill -f scripts/studio.py

set -euo pipefail
APP_NAME="Pistachio's Studio"
APP_PATH="/Applications/${APP_NAME}.app"
HERE="$(cd "$(dirname "$0")" && pwd)"

echo "Creating ${APP_NAME}.app in /Applications..."
rm -rf "${APP_PATH}"
TMP="$(mktemp -d)"
cat > "${TMP}/launch.applescript" <<APPLESCRIPT
property studioDir : "${HERE}"
property logFile : (POSIX path of (path to library folder from user domain)) & "Logs/Pistachios Studio.log"
property serverPid : ""
property studioURL : ""

on run
	startStudio()
end run

on reopen
	if studioURL is not "" then open location studioURL
end reopen

on startStudio()
	set cmd to "cd " & quoted form of studioDir & " && : > " & quoted form of logFile & " ; /bin/zsh -ic " & quoted form of "if [ -x .venv/bin/python ]; then exec .venv/bin/python scripts/studio.py --no-open --new-session; else exec python3 scripts/studio.py --no-open --new-session; fi" & " >> " & quoted form of logFile & " 2>&1 & echo \$!"
	set serverPid to do shell script cmd
	repeat 60 times
		delay 0.5
		try
			set u to do shell script "grep -o 'http://127.0.0.1:[0-9]*/?t=[^ ]*' " & quoted form of logFile & " | head -1"
			if u is not "" then
				set studioURL to u
				open location u
				return
			end if
		end try
	end repeat
	display alert "Pistachio's Studio did not start" message "Look at the log: " & logFile
	quit
end startStudio

on quit
	try
		do shell script "kill " & serverPid
	end try
	continue quit
end quit
APPLESCRIPT
osacompile -s -o "${APP_PATH}" "${TMP}/launch.applescript"

# Name, id and icon. The icon (a lime P and a coral S that touch) is drawn by scripts/make_icon.py.
PLIST="${APP_PATH}/Contents/Info.plist"
plutil -replace CFBundleName -string "${APP_NAME}" "${PLIST}"
plutil -replace CFBundleDisplayName -string "${APP_NAME}" "${PLIST}"
plutil -replace CFBundleIdentifier -string "com.pistachiosstudio.app" "${PLIST}"
plutil -replace CFBundleIconFile -string "applet" "${PLIST}"        # osacompile's default icon name
PYBIN=python3; [ -x "${HERE}/.venv/bin/python" ] && PYBIN="${HERE}/.venv/bin/python"      # install.sh puts Pillow in .venv
"$PYBIN" "${HERE}/scripts/make_icon.py" "${TMP}/icon" | sed -n 's/^wrote //p' | grep '\.icns$' | while read -r f; do
  cp "$f" "${APP_PATH}/Contents/Resources/applet.icns"
done

xattr -cr "${APP_PATH}" 2>/dev/null || true
codesign --force --deep --sign - "${APP_PATH}" 2>/dev/null || true     # a local (ad-hoc) signature
touch "${APP_PATH}"
rm -rf "${TMP}"
echo "Created ${APP_PATH}"
echo "You can now launch ${APP_NAME} from Applications or Spotlight."
