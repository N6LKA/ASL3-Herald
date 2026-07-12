<?php
require __DIR__ . '/../herald-common.php';

// api.github.com's Contents API is used instead of raw.githubusercontent.com -
// that CDN is known to serve stale content for extended periods even with
// cache-busting query strings (confirmed directly during unrelated work on
// this project's companion Allmon3 page). Reading through the API instead
// goes straight to git storage, no CDN layer in between.
define('HERALD_VERSION_FILE', '/usr/local/bin/asl3-herald/version.txt');
define('HERALD_VERSION_CHECK_URL', 'https://api.github.com/repos/N6LKA/asl3-herald/contents/version.txt?ref=main');

$current = trim((string) @file_get_contents(HERALD_VERSION_FILE));
if ($current === '') {
    $current = 'unknown';
}

// Prefer cURL - it works regardless of the allow_url_fopen ini setting,
// which is disabled by default on some hardened/minimal PHP installs (a
// likely cause if file_get_contents() ever silently fails here). Only fall
// back to file_get_contents() if the curl extension isn't loaded at all.
$latest_raw = false;
$fetch_error = '';

if (function_exists('curl_init')) {
    $ch = curl_init(HERALD_VERSION_CHECK_URL);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_HTTPHEADER => ['Accept: application/vnd.github.v3.raw', 'User-Agent: asl3-herald-update-check'],
        CURLOPT_TIMEOUT => 5,
        CURLOPT_FOLLOWLOCATION => true,
    ]);
    $result = curl_exec($ch);
    if ($result === false) {
        $fetch_error = curl_error($ch);
    } else {
        $latest_raw = $result;
    }
    curl_close($ch);
} elseif (ini_get('allow_url_fopen')) {
    $context = stream_context_create(['http' => [
        'method'  => 'GET',
        'header'  => "Accept: application/vnd.github.v3.raw\r\nUser-Agent: asl3-herald-update-check\r\n",
        'timeout' => 5,
    ]]);
    $latest_raw = @file_get_contents(HERALD_VERSION_CHECK_URL, false, $context);
    if ($latest_raw === false) {
        $fetch_error = 'file_get_contents() failed (network issue, or GitHub unreachable)';
    }
} else {
    $fetch_error = "PHP can't make outbound HTTPS requests: neither the curl extension nor allow_url_fopen is available. Install php-curl (sudo apt install php-curl && sudo systemctl restart apache2) to fix this.";
}

if ($latest_raw === false) {
    herald_json_response([
        'success' => false,
        'current_version' => $current,
        'message' => 'Could not reach GitHub to check for updates: ' . $fetch_error,
    ]);
}

$latest = trim($latest_raw);

// Three distinct states, not just "same or different" - installing from
// --branch develop (for testing ahead of a release) can leave the running
// version numerically ahead of main's latest release, which is neither
// "update available" nor really "up to date" in the usual sense.
$update_available = false;
$ahead_of_main = false;
if ($latest !== '' && $current !== 'unknown') {
    $cmp = version_compare($current, $latest); // -1, 0, or 1
    $update_available = $cmp < 0;
    $ahead_of_main = $cmp > 0;
}

herald_json_response([
    'success' => true,
    'current_version' => $current,
    'latest_version' => $latest,
    'update_available' => $update_available,
    'ahead_of_main' => $ahead_of_main,
]);
