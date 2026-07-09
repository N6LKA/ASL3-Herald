#!/usr/bin/env bash
# asl3-herald uninstall script
# Usage: curl -fsSL -H "Cache-Control: no-cache" https://raw.githubusercontent.com/N6LKA/asl3-herald/main/uninstall.sh | sudo bash
#   (the "sudo bash <(curl ...)" process-substitution form fails with
#    /dev/fd/63: No such file or directory on some systems — pipe instead)
#
# Options (pass after "--" when piping): --purge-config  --purge-piper  --purge-all
#   e.g. curl -fsSL ... | sudo bash -s -- --purge-all

set -euo pipefail

INSTALL_DIR="/usr/local/bin/asl3-herald"
CONFIG_DIR="/etc/asterisk/scripts/asl3-herald"
SERVICE_FILE="/etc/systemd/system/asl3-herald.service"
HERALD_BIN="/usr/local/bin/herald"
WEB_DIR="/var/www/html/asl3-herald"
SUDOERS_WEB="/etc/sudoers.d/asl3-herald-web"
MENU_INI="/etc/allmon3/menu.ini"
ALLMON3_CUSTOM_CSS="/etc/allmon3/custom.css"
SUPERMON_FOOTER="/var/www/html/supermon/footer.inc"
PIPER_DIR="/opt/piper"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

if [[ $EUID -ne 0 ]]; then
    error "This script must be run as root. Use: curl -fsSL ... | sudo bash"
fi

PURGE_CONFIG=false
PURGE_PIPER=false
for arg in "$@"; do
    case "$arg" in
        --purge-config) PURGE_CONFIG=true ;;
        --purge-piper)  PURGE_PIPER=true ;;
        --purge-all)    PURGE_CONFIG=true; PURGE_PIPER=true ;;
        *) warn "Unknown option: $arg" ;;
    esac
done

echo ""
echo "  asl3-herald uninstaller"
echo "  https://github.com/N6LKA/asl3-herald"
echo ""

# ── Service ────────────────────────────────────────────────────────────────────

if [[ -f "$SERVICE_FILE" ]]; then
    info "Stopping and disabling asl3-herald service..."
    systemctl stop asl3-herald 2>/dev/null || true
    systemctl disable asl3-herald 2>/dev/null || true
    rm -f "$SERVICE_FILE"
    systemctl daemon-reload 2>/dev/null || true
fi

# ── Daemon + CLI ───────────────────────────────────────────────────────────────

info "Removing daemon and herald command..."
rm -rf "$INSTALL_DIR"
rm -f "$HERALD_BIN"

# ── Web UI + sudoers ───────────────────────────────────────────────────────────

if [[ -d "$WEB_DIR" ]]; then
    info "Removing web UI ($WEB_DIR)..."
    rm -rf "$WEB_DIR"
fi

if [[ -f "$SUDOERS_WEB" ]]; then
    info "Removing sudoers rule ($SUDOERS_WEB)..."
    rm -f "$SUDOERS_WEB"
fi

# ── Allmon3 / Supermon integration ─────────────────────────────────────────────
# Surgical removal: only strips what asl3-herald's installer added, leaving
# the rest of each file (and any other customizations) untouched.

if [[ -f "$MENU_INI" ]] && grep -q "^\[Herald\]" "$MENU_INI"; then
    info "Removing [Herald] section from menu.ini..."
    cp "$MENU_INI" "$MENU_INI.bak.$(date +%Y%m%d-%H%M%S)"
    awk '
    BEGIN { skip = 0 }
    /^\[Herald\]$/ { skip = 1; next }
    skip && /^\[/ { skip = 0 }
    !skip { print }
    ' "$MENU_INI" > "$MENU_INI.tmp" && mv "$MENU_INI.tmp" "$MENU_INI"
    warn "Restart allmon3 to apply: sudo systemctl restart allmon3"
fi

if [[ -f "$ALLMON3_CUSTOM_CSS" ]] && grep -qF 'a[href*="asl3-herald"]' "$ALLMON3_CUSTOM_CSS"; then
    info "Removing asl3-herald login-hide rule from Allmon3 custom.css..."
    cp "$ALLMON3_CUSTOM_CSS" "$ALLMON3_CUSTOM_CSS.bak.$(date +%Y%m%d-%H%M%S)"
    grep -vF '/* asl3-herald: hide sidebar link until logged into Allmon3 */' "$ALLMON3_CUSTOM_CSS" | \
        grep -vF 'body.logged-out a[href*="asl3-herald"] { display: none !important; }' \
        > "$ALLMON3_CUSTOM_CSS.tmp" && mv "$ALLMON3_CUSTOM_CSS.tmp" "$ALLMON3_CUSTOM_CSS"
fi

if [[ -f "$SUPERMON_FOOTER" ]] && grep -q "asl3-herald/herald-frame-supermon.php" "$SUPERMON_FOOTER"; then
    info "Removing asl3-herald link from Supermon footer..."
    cp "$SUPERMON_FOOTER" "$SUPERMON_FOOTER.bak.$(date +%Y%m%d-%H%M%S)"
    grep -v "asl3-herald/herald-frame-supermon.php" "$SUPERMON_FOOTER" > "$SUPERMON_FOOTER.tmp" \
        && mv "$SUPERMON_FOOTER.tmp" "$SUPERMON_FOOTER"
    chown www-data:www-data "$SUPERMON_FOOTER" 2>/dev/null || true
fi

# ── Config / announcements / state (preserved by default) ─────────────────────

if [[ "$PURGE_CONFIG" == "true" ]]; then
    if [[ -d "$CONFIG_DIR" ]]; then
        warn "Purging config, announcements, and state ($CONFIG_DIR)..."
        rm -rf "$CONFIG_DIR"
    fi
elif [[ -d "$CONFIG_DIR" ]]; then
    info "Config, announcements, and state preserved at: $CONFIG_DIR"
    info "  (reinstalling later will pick this config back up)"
    info "  Remove manually with: sudo rm -rf $CONFIG_DIR"
fi

# ── Piper TTS (preserved by default — large download) ─────────────────────────

if [[ "$PURGE_PIPER" == "true" ]]; then
    if [[ -d "$PIPER_DIR" ]]; then
        warn "Purging Piper TTS ($PIPER_DIR)..."
        rm -rf "$PIPER_DIR"
    fi
elif [[ -d "$PIPER_DIR" ]]; then
    info "Piper TTS preserved at: $PIPER_DIR"
    info "  Remove manually with: sudo rm -rf $PIPER_DIR"
fi

# ── Summary ────────────────────────────────────────────────────────────────────

echo ""
echo -e "  ${GREEN}asl3-herald has been uninstalled.${NC}"
echo ""
echo "  Options for next time (pass after --  when piping through sudo bash -s):"
echo "    --purge-config   also remove config, announcements, and state"
echo "    --purge-piper    also remove the Piper TTS binary and voices"
echo "    --purge-all      both of the above"
echo ""
