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

$context = stream_context_create(['http' => [
    'method'  => 'GET',
    'header'  => "Accept: application/vnd.github.v3.raw\r\nUser-Agent: asl3-herald-update-check\r\n",
    'timeout' => 5,
]]);
$latest_raw = @file_get_contents(HERALD_VERSION_CHECK_URL, false, $context);

if ($latest_raw === false) {
    herald_json_response([
        'success' => false,
        'current_version' => $current,
        'message' => 'Could not reach GitHub to check for updates (no internet access, or GitHub unreachable)',
    ]);
}

$latest = trim($latest_raw);
$update_available = ($latest !== '' && $current !== 'unknown')
    ? version_compare($latest, $current, '>')
    : false;

herald_json_response([
    'success' => true,
    'current_version' => $current,
    'latest_version' => $latest,
    'update_available' => $update_available,
]);
