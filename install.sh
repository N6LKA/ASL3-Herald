#!/usr/bin/env bash
# asl3-herald install script
# Usage: bash <(curl -fsSL -H "Cache-Control: no-cache" https://raw.githubusercontent.com/N6LKA/asl3-herald/main/install.sh)

set -euo pipefail

REPO_RAW="https://raw.githubusercontent.com/N6LKA/asl3-herald/main"
INSTALL_DIR="/usr/local/bin/asl3-herald"
CONFIG_DIR="/etc/asterisk/scripts/asl3-herald"
ANNOUNCE_DIR="$CONFIG_DIR/announcements"
SERVICE_FILE="/etc/systemd/system/asl3-herald.service"
HERALD_BIN="/usr/local/bin/herald"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

if [[ $EUID -ne 0 ]]; then
    error "This installer must be run as root. Use: sudo bash <(curl ...)"
fi

echo ""
echo "  asl3-herald — Enhanced Tail Message & Announcement Daemon"
echo "  https://github.com/N6LKA/asl3-herald"
echo ""

# ── Dependencies ───────────────────────────────────────────────────────────────

info "Checking dependencies..."
apt-get update -qq

PKGS=()
command -v python3 &>/dev/null || PKGS+=(python3)
python3 -c "import yaml" 2>/dev/null     || PKGS+=(python3-yaml)
command -v sox &>/dev/null               || PKGS+=(sox)

if [[ ${#PKGS[@]} -gt 0 ]]; then
    info "Installing: ${PKGS[*]}"
    apt-get install -y -qq "${PKGS[@]}"
fi

# TTS check (optional — just warn if missing)
if ! command -v text2wave &>/dev/null && ! command -v espeak-ng &>/dev/null; then
    warn "No TTS engine found. 'herald add' will not work without one."
    warn "Install with:  sudo apt install festival sox"
    warn "           or: sudo apt install espeak-ng sox"
fi

# ── Install daemon files ───────────────────────────────────────────────────────

info "Installing daemon to $INSTALL_DIR ..."
mkdir -p "$INSTALL_DIR"

curl -fsSL -H "Cache-Control: no-cache" "$REPO_RAW/asl3-herald.py"   -o "$INSTALL_DIR/asl3-herald.py"
curl -fsSL -H "Cache-Control: no-cache" "$REPO_RAW/version.txt"      -o "$INSTALL_DIR/version.txt"
chmod +x "$INSTALL_DIR/asl3-herald.py"

# ── Herald management command ──────────────────────────────────────────────────

info "Installing herald command to $HERALD_BIN ..."
curl -fsSL -H "Cache-Control: no-cache" "$REPO_RAW/herald" -o "$HERALD_BIN"
chmod +x "$HERALD_BIN"

# ── Config directory ───────────────────────────────────────────────────────────

mkdir -p "$CONFIG_DIR" "$ANNOUNCE_DIR"

if [[ -f "$CONFIG_DIR/asl3-herald.conf" ]]; then
    warn "Config already exists — not overwriting: $CONFIG_DIR/asl3-herald.conf"
else
    info "Installing example config ..."
    curl -fsSL -H "Cache-Control: no-cache" "$REPO_RAW/asl3-herald.conf.example" \
        -o "$CONFIG_DIR/asl3-herald.conf"
    warn "Edit your config before starting: $CONFIG_DIR/asl3-herald.conf"
fi

# ── systemd service ────────────────────────────────────────────────────────────

info "Installing systemd service ..."
curl -fsSL -H "Cache-Control: no-cache" "$REPO_RAW/asl3-herald.service" -o "$SERVICE_FILE"
systemctl daemon-reload
systemctl enable asl3-herald

# ── Summary ────────────────────────────────────────────────────────────────────

VERSION=$(cat "$INSTALL_DIR/version.txt" 2>/dev/null || echo "unknown")
echo ""
echo -e "  ${GREEN}asl3-herald v${VERSION} installed successfully.${NC}"
echo ""
echo "  Next steps:"
echo "  1. Edit config:   nano $CONFIG_DIR/asl3-herald.conf"
echo "  2. Start service: sudo systemctl start asl3-herald"
echo "  3. Check status:  herald status"
echo "  4. Add a message: sudo herald add \"This is W1ABC, repeater ID.\" --name id"
echo ""
echo "  Manage:  herald <status|enable|disable|reload|add|add-file|list|remove|play>"
echo ""
