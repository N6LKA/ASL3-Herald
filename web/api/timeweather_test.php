<?php
require __DIR__ . '/../herald-common.php';

// Asks the already-running daemon to perform the test-play itself, rather
// than doing the weather-fetch/build/play work in this one-off PHP-spawned
// process. A process invoked through Apache/PHP (even via sudo - mount
// namespaces follow the process tree, not the UID) can inherit Apache's own
// PrivateTmp sandbox (common default), which hides data other programs
// write to /tmp (e.g. SkywarnPlus's shared weather file) from it. The
// daemon is a plain systemd service, never spawned by Apache, so it isn't
// affected - see cmd_request_test_timeweather in the herald script.
define('TW_TEST_RESULT_FILE', '/etc/asterisk/scripts/asl3-herald/timeweather-test-result.json');

// Optional message_id: the per-row Test button in the Custom Templates
// table passes this to force that specific message instead of the daemon's
// usual random pick - see the btn-test-tw-msg handler in herald-ui.js.
$input = json_decode(file_get_contents('php://input'), true) ?? [];
$args = ['request-timeweather-test'];
if (array_key_exists('message_id', $input) && $input['message_id'] !== '') {
    $messageId = trim((string) $input['message_id']);
    if (!preg_match('/^[a-f0-9]{6,40}$/', $messageId)) {
        herald_json_response(['success' => false, 'message' => 'Invalid message id'], 400);
    }
    $args[] = '--message-id';
    $args[] = $messageId;
}

$requestResult = herald_run_sudo($args);
$requestData = herald_extract_json($requestResult['stdout']);
if ($requestData === null || empty($requestData['success']) || empty($requestData['request_id'])) {
    $message = $requestData['message'] ?? trim($requestResult['stderr']) ?: 'Could not request a test play';
    herald_json_response(['success' => false, 'message' => $message], 500);
}
$requestId = $requestData['request_id'];

// Poll briefly for the daemon's result - it checks for the request on its
// own poll cycle (every 0.5s) and a full weather fetch + build should
// finish well within this window; 8s leaves generous headroom.
$deadline = microtime(true) + 8.0;
while (microtime(true) < $deadline) {
    if (is_file(TW_TEST_RESULT_FILE)) {
        $raw = @file_get_contents(TW_TEST_RESULT_FILE);
        $resultData = $raw !== false ? json_decode($raw, true) : null;
        if (is_array($resultData) && ($resultData['request_id'] ?? null) === $requestId) {
            unset($resultData['request_id']);
            herald_json_response($resultData);
        }
    }
    usleep(150000);
}

herald_json_response([
    'success' => false,
    'message' => 'Timed out waiting for the daemon to respond - check that asl3-herald is running, or check Playback History',
], 504);
