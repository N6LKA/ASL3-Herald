#!/usr/bin/env bash
# asl3-herald install script
# Usage: curl -fsSL -H "Cache-Control: no-cache" https://raw.githubusercontent.com/N6LKA/asl3-herald/main/install.sh | sudo bash
#   (the "sudo bash <(curl ...)" process-substitution form fails with
#    /dev/fd/63: No such file or directory on some systems — pipe instead.
#    This bootstrap fetch of install.sh itself can occasionally be served
#    stale by raw.githubusercontent.com's CDN, but that's low-stakes here -
#    once ANY reasonably-current install.sh runs, its own internal file
#    fetch (below) downloads the whole repo as one tarball from GitHub's
#    codeload service, which is neither CDN-cached per file nor subject to
#    the api.github.com REST API's 60-requests/hour rate limit - both of
#    which were hit and are worse failure modes than an occasionally-stale
#    bootstrap script.)
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

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# Downloads the whole repo at the given ref as a single tarball (GitHub's
# codeload service, not raw.githubusercontent.com) and extracts it once, up
# front - fetch_repo_file() below then just copies out of that local copy.
# Two problems this avoids, both hit while testing this installer itself:
#   1. raw.githubusercontent.com is fronted by a CDN (Fastly) that can serve
#      a stale cached copy of an individual file for an extended stretch,
#      even with a "Cache-Control: no-cache" request header and a
#      cache-busting query string.
#   2. Fetching each of the ~30 repo files individually through GitHub's
#      Contents API (the first fix for #1) burns through GitHub's 60
#      requests/hour unauthenticated rate limit after just two reinstalls -
#      a single tarball download is one request no matter how many files
#      the repo has.
REPO_TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$REPO_TMP_DIR"' EXIT

info "Downloading asl3-herald ($BRANCH) ..."
if ! curl -fsSL "https://github.com/N6LKA/asl3-herald/archive/refs/heads/${BRANCH}.tar.gz" -o "$REPO_TMP_DIR/repo.tar.gz"; then
    error "Could not download the asl3-herald repo archive for branch '$BRANCH'."
fi
tar -xzf "$REPO_TMP_DIR/repo.tar.gz" -C "$REPO_TMP_DIR" --strip-components=1

fetch_repo_file() {
    local path="$1" dest="$2"
    cp "$REPO_TMP_DIR/$path" "$dest"
}

INSTALL_DIR="/usr/local/bin/asl3-herald"
CONFIG_DIR="/etc/asterisk/scripts/asl3-herald"
ANNOUNCE_DIR="$CONFIG_DIR/announcements"
SERVICE_FILE="/etc/systemd/system/asl3-herald.service"
HERALD_BIN="/usr/local/bin/herald"

# Captured before anything is touched: if the service was already running,
# it's an update/reinstall (not a fresh install), so we restart it at the end
# to actually load the new code - `herald reload` (SIGHUP) only re-reads the
# YAML config into an already-running process, it can never pick up changes
# to asl3-herald.py itself. Re-running this installer alone was never enough
# to apply a code update; only a restart (or reboot) does.
WAS_ACTIVE=false
systemctl is-active --quiet asl3-herald 2>/dev/null && WAS_ACTIVE=true

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

fetch_repo_file "asl3-herald.py" "$INSTALL_DIR/asl3-herald.py"
fetch_repo_file "version.txt"    "$INSTALL_DIR/version.txt"
chmod +x "$INSTALL_DIR/asl3-herald.py"

# ── Herald management command ──────────────────────────────────────────────────

info "Installing herald command to $HERALD_BIN ..."
fetch_repo_file "herald" "$HERALD_BIN"
chmod +x "$HERALD_BIN"

# ── Config directory ───────────────────────────────────────────────────────────

mkdir -p "$CONFIG_DIR" "$ANNOUNCE_DIR"

if [[ -f "$CONFIG_DIR/asl3-herald.conf" ]]; then
    warn "Config already exists — not overwriting: $CONFIG_DIR/asl3-herald.conf"
else
    info "Installing example config ..."
    fetch_repo_file "asl3-herald.conf.example" "$CONFIG_DIR/asl3-herald.conf"

    # Interactive prompts for a brand-new config only - never touches an
    # existing one. Reads from /dev/tty rather than plain stdin, since this
    # script's own stdin is the curl|bash pipe, not the terminal; falls back
    # to leaving the field at its safe default/blank if no controlling
    # terminal is available (e.g. a fully unattended/scripted run).
    NODE_NUM=""
    if [[ -r /dev/tty ]]; then
        read -rp "Enter your ASL3/AllStarLink node number (required): " NODE_NUM < /dev/tty || true
    fi
    if [[ -n "$NODE_NUM" ]]; then
        if [[ "$NODE_NUM" =~ ^[0-9]+$ ]]; then
            sed -i "s/^Node: .*/Node: \"$NODE_NUM\"/" "$CONFIG_DIR/asl3-herald.conf"
            info "Node number set to $NODE_NUM."
        else
            warn "'$NODE_NUM' doesn't look like a node number (digits only) — leaving Node blank."
        fi
    else
        warn "No node number entered — leaving Node blank. The daemon will refuse to start until you set it."
    fi

    MIN_INTERVAL=""
    if [[ -r /dev/tty ]]; then
        read -rp "Minimum seconds between tail messages [default 300 = 5 min]: " MIN_INTERVAL < /dev/tty || true
    fi
    if [[ -n "$MIN_INTERVAL" ]]; then
        if [[ "$MIN_INTERVAL" =~ ^[0-9]+$ ]]; then
            sed -i "s/^  MinInterval: .*/  MinInterval: $MIN_INTERVAL/" "$CONFIG_DIR/asl3-herald.conf"
            info "MinInterval set to ${MIN_INTERVAL}s."
        else
            warn "'$MIN_INTERVAL' isn't a number — leaving MinInterval at the default (300s = 5 min)."
        fi
    fi

    warn "Review the rest of the config before starting: $CONFIG_DIR/asl3-herald.conf"
fi

# ── systemd service ────────────────────────────────────────────────────────────

info "Installing systemd service ..."
fetch_repo_file "asl3-herald.service" "$SERVICE_FILE"
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

# php-curl - needed for the Settings tab's "Check for Updates" button to make
# an outbound HTTPS request to GitHub. Checked/installed unconditionally
# regardless of what host app is detected, same reasoning as the php-curl
# check this installer used to do for an older Allmon3 auth check: some
# hosts have PHP/Apache already present (via Allmon3/Supermon) but still
# missing the curl extension specifically.
if ! php -r 'exit(function_exists("curl_init") ? 0 : 1);' 2>/dev/null; then
    info "Installing php-curl (needed for the update-check feature) ..."
    apt-get install -y -qq php-curl
    systemctl restart apache2 2>/dev/null || true
fi

info "Installing web UI to $WEB_DIR ..."
mkdir -p "$WEB_DIR/api" "$WEB_DIR/img"
for f in herald-common.php herald-ui-fragment.php herald-ui.js; do
    fetch_repo_file "web/$f" "$WEB_DIR/$f"
done
for f in list.php voices.php play.php reload.php toggle.php remove.php add_rotation.php add_scheduled.php edit_rotation.php edit_scheduled.php settings.php reorder_rotation.php playback_history.php clear_history.php config_export.php config_import.php version_check.php; do
    fetch_repo_file "web/api/$f" "$WEB_DIR/api/$f"
done
for f in asl3-herald-icon.svg asl3-herald-banner.svg; do
    fetch_repo_file "web/img/$f" "$WEB_DIR/img/$f"
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
        fetch_repo_file "web/allmon3/asl3-herald.html" "$ALLMON3_WEB_ROOT/asl3-herald.html"
        chown root:root "$ALLMON3_WEB_ROOT/asl3-herald.html" 2>/dev/null || true
        chmod 644 "$ALLMON3_WEB_ROOT/asl3-herald.html"
    else
        warn "Allmon3 web root not found at $ALLMON3_WEB_ROOT — skipping Allmon3 page install"
        warn "(this is expected only on a non-standard Allmon3 install)"
    fi

    # menu.ini — appended to the END of the file so it never disturbs existing
    # custom menu entries; idempotent (skips if a [Herald] section already exists).
    MENU_INI_CHANGED=false
    if [[ -f "$MENU_INI" ]] && grep -q "^\[Herald\]" "$MENU_INI"; then
        info "Allmon3 menu.ini already has a [Herald] entry — skipping"
    else
        MENU_INI_CHANGED=true
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

    # Allmon3 reads menu.ini into memory at startup, same reasoning as the
    # asl3-herald daemon itself needing a restart (not just a config
    # reload) to pick up a change made to a file on disk - only restart when
    # the section was actually just added, never when it already existed
    # (a plain reinstall shouldn't bounce Allmon3 for no reason).
    if $MENU_INI_CHANGED && systemctl is-active --quiet allmon3 2>/dev/null; then
        info "Restarting allmon3 to pick up the new sidebar link ..."
        systemctl restart allmon3
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
    fetch_repo_file "web/supermon/asl3-herald.php" "$SUPERMON_DIR/asl3-herald.php"
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

# ── Restart if this was an update to an already-running install ────────────────
# `herald reload` (SIGHUP) only re-reads the YAML config, never the daemon's
# own code - a code update (like this one) needs an actual process restart to
# take effect. Only done when the service was already active before this run,
# so a genuinely fresh install still starts with an unedited example config
# only once the user is ready (per "Next steps" below).
if $WAS_ACTIVE; then
    info "asl3-herald was already running — restarting to load the updated code ..."
    systemctl restart asl3-herald
fi

# ── Summary ────────────────────────────────────────────────────────────────────

VERSION=$(cat "$INSTALL_DIR/version.txt" 2>/dev/null || echo "unknown")
echo ""
echo -e "  ${GREEN}asl3-herald v${VERSION} installed successfully.${NC}"
echo ""
if $WAS_ACTIVE; then
    echo "  Service was already running and has been restarted to pick up this update."
    echo "  Check status:  herald status"
else
    echo "  Next steps:"
    echo "  1. Edit config:   nano $CONFIG_DIR/asl3-herald.conf"
    echo "  2. Start service: sudo systemctl start asl3-herald"
    echo "  3. Check status:  herald status"
    echo "  4. Add a message: sudo herald add \"This is W1ABC, repeater ID.\" --name id"
    echo "  5. List voices:   herald voices"
fi
echo ""
echo "  Manage:  herald <status|enable|disable|reload|voices|add|add-file|list|remove|play|add-schedule|add-schedule-file|reorder-rotation|playback-history|export-config|import-config>"
echo ""
echo "  Web UI:  installed to $WEB_DIR"
if [[ -d /etc/allmon3 ]]; then
    echo "           Allmon3 — look for the \"Announcement Settings\" link in the sidebar"
    echo "           (added to the bottom of $MENU_INI; allmon3 was restarted automatically"
    echo "            if the link was just added)"
fi
if [[ -f "$SUPERMON_FOOTER" ]]; then
    echo "           Supermon — look for the \"ASL3 Herald\" link at the bottom after logging in"
fi
echo ""
