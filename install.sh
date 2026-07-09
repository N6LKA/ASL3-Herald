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
dpkg -s libsox-fmt-mp3 &>/dev/null        || PKGS+=(libsox-fmt-mp3)

if [[ ${#PKGS[@]} -gt 0 ]]; then
    info "Installing: ${PKGS[*]}"
    apt-get install -y -qq "${PKGS[@]}"
fi

# ── Piper TTS (neural voices, preferred) ───────────────────────────────────────

PIPER_BIN="/opt/piper/bin/piper/piper"
PIPER_VOICE_DIR="/opt/piper/voices"

if [[ -f "$PIPER_BIN" && -x "$PIPER_BIN" ]]; then
    info "Piper TTS already installed at $PIPER_BIN — skipping download"
else
    info "Installing Piper TTS 1.2.0 (neural voices)..."
    ARCH=$(uname -m)
    if [[ "$ARCH" == "x86_64" || "$ARCH" == "amd64" ]]; then
        PIPER_FILE="piper_amd64.tar.gz"
    elif [[ "$ARCH" == "aarch64" || "$ARCH" == "arm64" ]]; then
        PIPER_FILE="piper_arm64.tar.gz"
    else
        warn "Unsupported architecture for Piper: $ARCH — will fall back to festival/espeak-ng"
        PIPER_FILE=""
    fi

    if [[ -n "$PIPER_FILE" ]]; then
        curl -fsSL "https://github.com/rhasspy/piper/releases/download/v1.2.0/$PIPER_FILE" \
            -o /tmp/piper.tar.gz
        mkdir -p /opt/piper/bin
        tar -xzf /tmp/piper.tar.gz -C /opt/piper/bin
        chmod +x "$PIPER_BIN"
        rm -f /tmp/piper.tar.gz
        info "Piper binary installed at $PIPER_BIN"
    fi
fi

if [[ -x "$PIPER_BIN" ]]; then
    info "Downloading default Piper voices (this may take a few minutes)..."
    mkdir -p "$PIPER_VOICE_DIR"
    BASE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main"

    download_voice() {
        local onnx_file="$1" model_path="$2" json_path="$3"
        if [[ -f "$PIPER_VOICE_DIR/$onnx_file" && -f "$PIPER_VOICE_DIR/$onnx_file.json" ]]; then
            return
        fi
        curl -fsSL "$BASE_URL/$model_path"  -o "$PIPER_VOICE_DIR/$onnx_file"
        curl -fsSL "$BASE_URL/$json_path"   -o "$PIPER_VOICE_DIR/$onnx_file.json"
    }

    download_voice "en_US-lessac-medium.onnx"     "en/en_US/lessac/medium/en_US-lessac-medium.onnx"         "en/en_US/lessac/medium/en_US-lessac-medium.onnx.json"
    download_voice "en_US-joe-medium.onnx"        "en/en_US/joe/medium/en_US-joe-medium.onnx"               "en/en_US/joe/medium/en_US-joe-medium.onnx.json"
    download_voice "en_US-amy-medium.onnx"        "en/en_US/amy/medium/en_US-amy-medium.onnx"               "en/en_US/amy/medium/en_US-amy-medium.onnx.json"
    download_voice "en_US-kristin-medium.onnx"    "en/en_US/kristin/medium/en_US-kristin-medium.onnx"       "en/en_US/kristin/medium/en_US-kristin-medium.onnx.json"
    download_voice "en_US-libritts_r-medium.onnx" "en/en_US/libritts_r/medium/en_US-libritts_r-medium.onnx" "en/en_US/libritts_r/medium/en_US-libritts_r-medium.onnx.json"
    download_voice "en_US-ryan-low.onnx"          "en/en_US/ryan/low/en_US-ryan-low.onnx"                   "en/en_US/ryan/low/en_US-ryan-low.onnx.json"

    chmod 644 "$PIPER_VOICE_DIR"/*.onnx "$PIPER_VOICE_DIR"/*.onnx.json 2>/dev/null || true
    info "Piper voices installed: lessac, joe, amy, kristin, libritts_r, ryan"
else
    warn "Piper TTS not available. 'herald add' will fall back to festival or espeak-ng if installed."
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
    CONFIG_PREEXISTED=true
    warn "Config already exists — not overwriting: $CONFIG_DIR/asl3-herald.conf"
else
    CONFIG_PREEXISTED=false
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

# ── Web UI ────────────────────────────────────────────────────────────────

WEB_DIR="/var/www/html/asl3-herald"
SUDOERS_WEB="/etc/sudoers.d/asl3-herald-web"
ALLMON3_INI="/etc/allmon3/allmon3.ini"
SUPERMON_FOOTER="/var/www/html/supermon/footer.inc"

if [[ ! -d /etc/allmon3 && ! -d /var/www/html/supermon ]]; then
    info "Neither Allmon3 nor Supermon detected — installing apache2 + php for the web UI"
    apt-get install -y -qq apache2 libapache2-mod-php php php-common
    systemctl enable --now apache2
fi

# Allmon3 does NOT bundle PHP the way Supermon does, so its presence alone
# doesn't guarantee php-curl is installed (needed for the Allmon3 auth check
# in herald-frame-allmon3.php). Ensure it unconditionally.
if ! php -r 'exit(function_exists("curl_init") ? 0 : 1);' 2>/dev/null; then
    info "Installing php-curl (required for the Allmon3 auth check)..."
    apt-get install -y -qq php-curl
    systemctl restart apache2 2>/dev/null || true
fi

info "Installing web UI to $WEB_DIR ..."
mkdir -p "$WEB_DIR/api"
for f in herald-ui.inc herald-common.php herald-frame-allmon3.php herald-frame-supermon.php; do
    curl -fsSL -H "Cache-Control: no-cache" "$REPO_RAW/web/$f" -o "$WEB_DIR/$f"
done
for f in list.php voices.php play.php reload.php toggle.php remove.php add_rotation.php add_scheduled.php; do
    curl -fsSL -H "Cache-Control: no-cache" "$REPO_RAW/web/api/$f" -o "$WEB_DIR/api/$f"
done
chown -R www-data:www-data "$WEB_DIR"
find "$WEB_DIR" -type f \( -name "*.php" -o -name "*.inc" \) -exec chmod 644 {} \;

info "Writing sudoers rule for www-data (herald command only) ..."
cat > "$SUDOERS_WEB" << EOF
# $SUDOERS_WEB
# managed by asl3-herald install.sh — do not edit manually
www-data ALL=(root) NOPASSWD: $HERALD_BIN
EOF
chmod 0440 "$SUDOERS_WEB"
chown root:root "$SUDOERS_WEB"

# Allmon3 iframe integration — only auto-patched when a real node number is
# already known (i.e. this is an upgrade of an existing install). Fresh
# installs get printed instructions instead of a guess at the node number.
if [[ -f "$ALLMON3_INI" ]]; then
    if [[ "$CONFIG_PREEXISTED" == "true" ]]; then
        NODE_NUMBER=$(grep -E '^Node:' "$CONFIG_DIR/asl3-herald.conf" | awk '{print $2}' | tr -d '"')
    else
        NODE_NUMBER=""
    fi

    if [[ -n "$NODE_NUMBER" ]]; then
        ALREADY_CONFIGURED=$(awk -v node="$NODE_NUMBER" '
            BEGIN { in_section=0; found=0 }
            {
                if ($0 ~ "^\\[") { in_section = ($0 ~ "^\\[" node "\\]$") }
                else if (in_section && $0 ~ "^iframepost") { found = 1 }
            }
            END { print found }
        ' "$ALLMON3_INI")

        if [[ "$ALREADY_CONFIGURED" == "1" ]]; then
            info "Allmon3 iframe already configured for node $NODE_NUMBER — skipping"
        else
            info "Adding asl3-herald iframe to Allmon3 node [$NODE_NUMBER] ..."
            cp "$ALLMON3_INI" "$ALLMON3_INI.bak.$(date +%Y%m%d-%H%M%S)"
            awk -v node="$NODE_NUMBER" '
            {
                if (in_section && $0 ~ "^\\[") {
                    print "iframepost=/asl3-herald/herald-frame-allmon3.php"
                    inserted = 1
                    in_section = 0
                }
                print $0
                if ($0 ~ "^\\[" node "\\]$") { in_section = 1 }
            }
            END {
                if (in_section && !inserted) {
                    print "iframepost=/asl3-herald/herald-frame-allmon3.php"
                }
            }
            ' "$ALLMON3_INI" > "$ALLMON3_INI.tmp" && mv "$ALLMON3_INI.tmp" "$ALLMON3_INI"
            info "Allmon3 iframe added for node $NODE_NUMBER. Restart allmon3: sudo systemctl restart allmon3"
        fi
    else
        warn "Allmon3 detected, but your node number isn't set yet in $CONFIG_DIR/asl3-herald.conf"
        warn "After editing your config, add this line under your node's section in $ALLMON3_INI:"
        warn "  iframepost=/asl3-herald/herald-frame-allmon3.php"
    fi
fi

# Supermon integration — add a link to the herald web UI in the logged-in
# footer, rather than inlining the whole UI (it lives in its own directory
# and gates itself with its own session check).
if [[ -f "$SUPERMON_FOOTER" ]]; then
    if grep -q "asl3-herald/herald-frame-supermon.php" "$SUPERMON_FOOTER"; then
        info "Supermon footer link already present — skipping"
    else
        info "Adding asl3-herald link to Supermon footer ..."
        cp "$SUPERMON_FOOTER" "$SUPERMON_FOOTER.bak.$(date +%Y%m%d-%H%M%S)"
        awk '
        /if \(\$_SESSION\['"'"'sm61loggedin'"'"'\] === true\) \{/ { print; inblock = 1; next }
        inblock && /^\s*\?>\s*$/ {
            print
            print "<a href=\"/asl3-herald/herald-frame-supermon.php\" target=\"_blank\">ASL3 Herald</a><br><br>"
            inblock = 0
            next
        }
        { print }
        ' "$SUPERMON_FOOTER" > "$SUPERMON_FOOTER.tmp" && mv "$SUPERMON_FOOTER.tmp" "$SUPERMON_FOOTER"
        chown www-data:www-data "$SUPERMON_FOOTER" 2>/dev/null || true
        info "Supermon footer link added."
    fi
fi

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
echo "  5. List voices:   herald voices"
echo ""
echo "  Manage:  herald <status|enable|disable|reload|voices|add|add-file|list|remove|play|add-schedule|add-schedule-file>"
echo ""
echo "  Web UI:  installed to $WEB_DIR"
if [[ -f "$ALLMON3_INI" ]]; then
    echo "           Allmon3 — check the node's page for the ASL3 Herald panel"
    echo "           (restart allmon3 if it was just added: sudo systemctl restart allmon3)"
fi
if [[ -f "$SUPERMON_FOOTER" ]]; then
    echo "           Supermon — look for the \"ASL3 Herald\" link at the bottom after logging in"
fi
echo ""
