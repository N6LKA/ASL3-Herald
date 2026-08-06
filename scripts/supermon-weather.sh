#!/usr/bin/env bash
# Supermon weather-line wrapper, installed by asl3-herald's install.sh as the
# target of the /usr/local/sbin/supermon/weather.sh symlink. Supermon's own
# link.php calls that path directly:
#
#   $WX = exec("/usr/local/sbin/supermon/weather.sh $LOCALZIP v");
#
# PHP's exec() only returns the process's last line of stdout, so this must
# always print exactly one line. Rather than fetching weather independently
# (a second, possibly-drifting source), this reads the same snapshot Herald
# already writes for Allmon3 (TimeWeather.Weather.SnapshotEnable in
# asl3-herald.conf) — so Supermon and Allmon3 always agree.
#
# Requires TimeWeather.Weather.SnapshotEnable: true in asl3-herald.conf.
# Without it, Herald never writes the snapshot file this reads, and this
# script prints "Weather data unavailable".

set -euo pipefail

CONF="/etc/asterisk/scripts/asl3-herald/asl3-herald.conf"
DEFAULT_SNAPSHOT_PATH="/tmp/asl3-herald/weather.json"
MAX_AGE_MIN=30

SNAPSHOT_PATH="$DEFAULT_SNAPSHOT_PATH"
if [[ -f "$CONF" ]]; then
    configured="$(grep -m1 'SnapshotPath:' "$CONF" 2>/dev/null \
        | sed 's/^[^:]*:[[:space:]]*//' | tr -d '"'"'"'' | xargs || true)"
    [[ -n "$configured" ]] && SNAPSHOT_PATH="$configured"
fi

python3 - "$SNAPSHOT_PATH" "$MAX_AGE_MIN" <<'PYEOF'
import json, os, sys, time

path, max_age_min = sys.argv[1], float(sys.argv[2])

try:
    age_min = (time.time() - os.path.getmtime(path)) / 60
    with open(path) as f:
        data = json.load(f)
    w = data.get("weather") or {}
    if age_min > max_age_min:
        raise ValueError("stale")
    if w.get("temp_f") is None:
        raise ValueError("incomplete")
except Exception:
    print("Weather data unavailable")
    sys.exit(0)

temp_f = w["temp_f"]
temp_c = round((temp_f - 32) * 5 / 9)
line = f"{temp_f}°F, {temp_c}°C"

humidity = w.get("humidity")
if humidity is not None:
    line += f", {humidity}% RH"

condition = (w.get("condition") or "").strip()
if condition:
    line += f" / {condition[0].upper()}{condition[1:]}"

wind_mph = w.get("wind_mph")
if wind_mph:
    wind_part = f"Wind {wind_mph} mph"
    wind_dir = w.get("wind_dir")
    if wind_dir:
        wind_part += f" {wind_dir}"
    gust_mph = w.get("wind_gust_mph")
    if gust_mph and gust_mph > wind_mph:
        wind_part += f" (gust {gust_mph})"
    line += f", {wind_part}"

print(line)
PYEOF
