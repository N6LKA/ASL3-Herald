<?php
require __DIR__ . '/../herald-common.php';

if ($_SERVER['REQUEST_METHOD'] === 'GET') {
    $result = herald_run(['list-json']);
    $data = json_decode(trim($result['stdout']), true);
    if ($data === null) {
        herald_json_response(['success' => false, 'message' => 'Could not read settings'], 500);
    }
    herald_json_response(array_merge(['success' => true], $data));
}

$input = json_decode(file_get_contents('php://input'), true) ?? [];

$node = trim($input['node'] ?? '');
if ($node === '' || !preg_match('/^[a-zA-Z0-9]{1,20}$/', $node)) {
    herald_json_response(['success' => false, 'message' => 'Invalid node number'], 400);
}

$pollInterval = filter_var($input['poll_interval'] ?? null, FILTER_VALIDATE_INT);
if ($pollInterval === false || $pollInterval < 1) {
    herald_json_response(['success' => false, 'message' => 'Invalid poll interval'], 400);
}

$debug = ($input['debug'] ?? false) ? 'true' : 'false';

$minInterval = filter_var($input['min_interval'] ?? null, FILTER_VALIDATE_INT);
if ($minInterval === false || $minInterval < 0) {
    herald_json_response(['success' => false, 'message' => 'Invalid min interval'], 400);
}

$swpEnable = ($input['swp_enable'] ?? false) ? 'true' : 'false';

$swpWxFile = trim($input['swp_wxfile'] ?? '');
if ($swpWxFile === '' || !preg_match('#^/[a-zA-Z0-9_./-]+$#', $swpWxFile)) {
    herald_json_response(['success' => false, 'message' => 'Invalid SkywarnPlus wx-tail file path'], 400);
}

$swpThreshold = filter_var($input['swp_threshold'] ?? null, FILTER_VALIDATE_INT);
if ($swpThreshold === false || $swpThreshold < 0) {
    herald_json_response(['success' => false, 'message' => 'Invalid silence threshold'], 400);
}

herald_respond_from_cli(herald_run_sudo([
    'update-settings',
    '--node', $node,
    '--poll-interval', (string) $pollInterval,
    '--debug', $debug,
    '--min-interval', (string) $minInterval,
    '--swp-enable', $swpEnable,
    '--swp-wxfile', $swpWxFile,
    '--swp-threshold', (string) $swpThreshold,
]));
