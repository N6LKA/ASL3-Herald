#!/usr/bin/env bash
# asl3-herald install script
# Usage: curl -fsSL -H "Cache-Control: no-cache" https://raw.githubusercontent.com/N6LKA/asl3-herald/main/install.sh | sudo bash
#   (the "sudo bash <(curl ...)" process-substitution form fails with
#    /dev/fd/63: No such file or directory on some systems — pipe instead)
#
# To test unreleased changes from the develop branch instead of main:
#   curl -fsSL -H "Cache-Control: no-cache" https://raw.githubusercontent.com/N6LKA/asl3-herald/develop/install.sh | sudo bash -s -- --branch develop
#   (pass --branch as a script argument, not an env var - env vars set before
#    "sudo" on a piped command don't reliably survive the sudo call on every
#    system, but args after "bash -s --" always do)

set -euo pipefail

BRANCH="main"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --branch) BRANCH="$2"; shift 2 ;;
        *) shift ;;
    esac
done

REPO_RAW="https://raw.githubusercontent.com/N6LKA/asl3-herald/${BRANCH}"
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
    error "This installer must be run as root. Use: curl -fsSL ... | sudo bash"
fi

echo ""
echo "  asl3-herald — Enhanced Tail Message & Announcement Daemon"
echo "  https://github.com/N6LKA/asl3-herald"
[[ "$BRANCH" != "main" ]] && warn "Installing from branch: $BRANCH (not main)"
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

# ── Web UI ─────────────────────────────────────────────────────────────────────

WEB_DIR="/var/www/html/asl3-herald"
SUDOERS_WEB="/etc/sudoers.d/asl3-herald-web"
SUPERMON_FOOTER="/var/www/html/supermon/footer.inc"

if [[ ! -d /etc/allmon3 && ! -d /var/www/html/supermon ]]; then
    info "Neither Allmon3 nor Supermon detected — installing apache2 + php for the web UI"
    apt-get install -y -qq apache2 libapache2-mod-php php php-common
    systemctl enable --now apache2
fi

info "Installing web UI to $WEB_DIR ..."
mkdir -p "$WEB_DIR/api" "$WEB_DIR/img"
for f in herald-common.php herald-ui-fragment.php herald-ui.js; do
    curl -fsSL -H "Cache-Control: no-cache" "$REPO_RAW/web/$f" -o "$WEB_DIR/$f"
done
for f in list.php voices.php play.php reload.php toggle.php remove.php add_rotation.php add_scheduled.php edit_rotation.php edit_scheduled.php settings.php; do
    curl -fsSL -H "Cache-Control: no-cache" "$REPO_RAW/web/api/$f" -o "$WEB_DIR/api/$f"
done
for f in asl3-herald-icon.svg asl3-herald-banner.svg; do
    curl -fsSL -H "Cache-Control: no-cache" "$REPO_RAW/web/img/$f" -o "$WEB_DIR/img/$f"
done
chown -R www-data:www-data "$WEB_DIR"
find "$WEB_DIR" -type f \( -name "*.php" -o -name "*.inc" -o -name "*.js" -o -name "*.svg" \) -exec chmod 644 {} \;

info "Writing sudoers rule for www-data (herald command only) ..."
cat > "$SUDOERS_WEB" << EOF
# $SUDOERS_WEB
# managed by asl3-herald install.sh — do not edit manually
www-data ALL=(root) NOPASSWD: $HERALD_BIN
EOF
chmod 0440 "$SUDOERS_WEB"
chown root:root "$SUDOERS_WEB"

# Allmon3 integration — a dedicated page installed directly into Allmon3's
# own web root (not /asl3-herald/), so it can load Allmon3's real
# functions.js/index.js unmodified for chrome + login detection. A page
# living outside Allmon3's own directory can't reliably read Allmon3's
# session cookie server-side (its Path is scoped to Allmon3's own API
# prefix), so this is a functional requirement, not just cosmetic.
ALLMON3_WEB_ROOT="/usr/share/allmon3"
MENU_INI="/etc/allmon3/menu.ini"
if [[ -d /etc/allmon3 ]]; then
    if [[ -d "$ALLMON3_WEB_ROOT" ]]; then
        info "Installing Allmon3 Announcement Settings page to $ALLMON3_WEB_ROOT ..."
        curl -fsSL -H "Cache-Control: no-cache" "$REPO_RAW/web/allmon3/asl3-herald.html" \
            -o "$ALLMON3_WEB_ROOT/asl3-herald.html"
        chown root:root "$ALLMON3_WEB_ROOT/asl3-herald.html" 2>/dev/null || true
        chmod 644 "$ALLMON3_WEB_ROOT/asl3-herald.html"
    else
        warn "Allmon3 web root not found at $ALLMON3_WEB_ROOT — skipping Allmon3 page install"
        warn "(this is expected only on a non-standard Allmon3 install)"
    fi

    # menu.ini — appended to the END of the file so it never disturbs existing
    # custom menu entries; idempotent (skips if a [Herald] section already exists).
    if [[ -f "$MENU_INI" ]] && grep -q "^\[Herald\]" "$MENU_INI"; then
        info "Allmon3 menu.ini already has a [Herald] entry — skipping"
    else
        info "Adding ASL3 Herald sidebar link to $MENU_INI ..."
        if [[ -f "$MENU_INI" ]]; then
            cp "$MENU_INI" "$MENU_INI.bak.$(date +%Y%m%d-%H%M%S)"
        else
            touch "$MENU_INI"
        fi
        if [[ -s "$MENU_INI" ]]; then
            # Ensure the file ends with a newline, then add a blank line as a
            # separator, so the new section doesn't run up against the last line.
            [[ -n "$(tail -c1 "$MENU_INI")" ]] && echo >> "$MENU_INI"
            echo >> "$MENU_INI"
        fi
        cat >> "$MENU_INI" << 'EOF'
[Herald]
type = single
Announcement Settings = /allmon3/asl3-herald.html
EOF
        info "Added to the bottom of $MENU_INI — move/relabel it there if you'd like it elsewhere"
    fi

    # custom.css — hides the sidebar link until logged into Allmon3. Cosmetic
    # only; asl3-herald.html itself still gates its content on real login
    # status regardless of whether the link is visible.
    CUSTOM_CSS="/etc/allmon3/custom.css"
    CSS_RULE='body.logged-out a[href*="asl3-herald"] { display: none !important; }'
    if [[ -f "$CUSTOM_CSS" ]] && grep -qF "$CSS_RULE" "$CUSTOM_CSS"; then
        info "Allmon3 custom.css already hides the Herald link when logged out — skipping"
    else
        info "Adding login-hide rule to $CUSTOM_CSS ..."
        if [[ -f "$CUSTOM_CSS" ]]; then
            cp "$CUSTOM_CSS" "$CUSTOM_CSS.bak.$(date +%Y%m%d-%H%M%S)"
        else
            touch "$CUSTOM_CSS"
        fi
        if [[ -s "$CUSTOM_CSS" ]]; then
            [[ -n "$(tail -c1 "$CUSTOM_CSS")" ]] && echo >> "$CUSTOM_CSS"
            echo >> "$CUSTOM_CSS"
        fi
        cat >> "$CUSTOM_CSS" << EOF
/* asl3-herald: hide sidebar link until logged into Allmon3 */
$CSS_RULE
EOF
    fi
fi

# Supermon integration — a dedicated page installed directly into Supermon's
# own directory (not /asl3-herald/), so it can include Supermon's real
# session.inc/header.inc/footer.inc unmodified. Supermon's session cookie is
# named "supermon61" (set by session.inc) — a page living outside Supermon's
# own directory that calls plain session_start() reads a different cookie
# (PHP's default PHPSESSID) and never sees the real login state, so this is
# a functional requirement, not just cosmetic.
SUPERMON_DIR="/var/www/html/supermon"
if [[ -d "$SUPERMON_DIR" ]]; then
    info "Installing Supermon Announcement Settings page to $SUPERMON_DIR ..."
    curl -fsSL -H "Cache-Control: no-cache" "$REPO_RAW/web/supermon/asl3-herald.php" \
        -o "$SUPERMON_DIR/asl3-herald.php"
    chown www-data:www-data "$SUPERMON_DIR/asl3-herald.php" 2>/dev/null || true
    chmod 644 "$SUPERMON_DIR/asl3-herald.php"
fi

# Supermon footer link — added inside Supermon's own login-conditional
# block, so it's already hidden until logged in, natively.
if [[ -f "$SUPERMON_FOOTER" ]]; then
    if grep -q "asl3-herald.php" "$SUPERMON_FOOTER"; then
        info "Supermon footer link already present — skipping"
    else
        info "Adding asl3-herald link to Supermon footer ..."
        cp "$SUPERMON_FOOTER" "$SUPERMON_FOOTER.bak.$(date +%Y%m%d-%H%M%S)"
        awk '
        /if \(\$_SESSION\['"'"'sm61loggedin'"'"'\] === true\) \{/ { print; inblock = 1; next }
        inblock && /^\s*\?>\s*$/ {
            print
            print "<a href=\"/supermon/asl3-herald.php\">ASL3 Herald</a><br><br>"
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
if [[ -d /etc/allmon3 ]]; then
    echo "           Allmon3 — look for the \"Announcement Settings\" link in the sidebar"
    echo "           (added to the bottom of $MENU_INI; restart allmon3 if it was just added:"
    echo "            sudo systemctl restart allmon3)"
fi
if [[ -f "$SUPERMON_FOOTER" ]]; then
    echo "           Supermon — look for the \"ASL3 Herald\" link at the bottom after logging in"
fi
echo ""
