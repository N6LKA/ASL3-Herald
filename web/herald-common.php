<?php
// herald-common.php — shared helpers for asl3-herald's web API endpoints.
// Not directly web-accessible logic on its own; included by web/api/*.php.

define('HERALD_BIN', '/usr/local/bin/herald');

function herald_json_response($data, int $code = 200): void {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode($data);
    exit;
}

function herald_valid_name(string $name): bool {
    return (bool) preg_match('/^[a-zA-Z0-9_-]{1,60}$/', $name);
}

function herald_exec_cmd(array $argv): array {
    $cmd = implode(' ', array_map('escapeshellarg', $argv));
    $descriptors = [1 => ['pipe', 'w'], 2 => ['pipe', 'w']];
    $proc = proc_open($cmd, $descriptors, $pipes);
    if (!is_resource($proc)) {
        return ['stdout' => '', 'stderr' => 'Failed to launch command', 'exit_code' => 1];
    }
    $stdout = stream_get_contents($pipes[1]);
    $stderr = stream_get_contents($pipes[2]);
    fclose($pipes[1]);
    fclose($pipes[2]);
    $exit_code = proc_close($proc);
    return ['stdout' => $stdout, 'stderr' => $stderr, 'exit_code' => $exit_code];
}

// Read-only commands — no sudo needed (config file is world-readable).
function herald_run(array $args): array {
    return herald_exec_cmd(array_merge([HERALD_BIN], $args));
}

// Mutating commands — run as root via the narrow sudoers rule for HERALD_BIN.
function herald_run_sudo(array $args): array {
    return herald_exec_cmd(array_merge(['sudo', HERALD_BIN], $args));
}

// herald's mutating subcommands print one JSON line (from asl3-herald.py)
// plus extra human-readable status lines (e.g. from cmd_reload). Scan from
// the end for the last line that parses as JSON.
function herald_extract_json(string $stdout): ?array {
    $lines = array_reverse(explode("\n", trim($stdout)));
    foreach ($lines as $line) {
        $line = trim($line);
        if ($line === '') continue;
        $decoded = json_decode($line, true);
        if (is_array($decoded)) return $decoded;
    }
    return null;
}

function herald_respond_from_cli(array $result): void {
    $data = herald_extract_json($result['stdout']);
    if ($data !== null) {
        herald_json_response($data);
    }
    herald_json_response([
        'success' => $result['exit_code'] === 0,
        'message' => trim($result['stdout']) !== '' ? trim($result['stdout']) : trim($result['stderr']),
    ]);
}

// Saves an uploaded file and converts it to 8kHz mono 16-bit WAV via sox.
// Returns the path to the converted temp file, or null on failure. Caller
// is responsible for deleting the returned file after use.
function herald_handle_upload(array $file): ?string {
    if (!isset($file['tmp_name']) || !is_uploaded_file($file['tmp_name'])) {
        return null;
    }
    $ext = strtolower(pathinfo($file['name'] ?? '', PATHINFO_EXTENSION));
    if (!in_array($ext, ['wav', 'mp3'], true)) {
        return null;
    }
    $dest = sys_get_temp_dir() . '/herald_upload_' . bin2hex(random_bytes(8)) . '.wav';
    $cmd = 'sox ' . escapeshellarg($file['tmp_name']) . ' -r 8000 -c 1 -b 16 -t wav ' . escapeshellarg($dest) . ' 2>&1';
    exec($cmd, $out, $ret);
    if ($ret !== 0 || !file_exists($dest)) {
        return null;
    }
    return $dest;
}
