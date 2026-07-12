<?php
require __DIR__ . '/../herald-common.php';

if (!isset($_FILES['file'])) {
    herald_json_response(['success' => false, 'message' => 'No file uploaded'], 400);
}
$tmp = $_FILES['file']['tmp_name'] ?? '';
if (!is_uploaded_file($tmp)) {
    herald_json_response(['success' => false, 'message' => 'Upload failed'], 400);
}

$decoded = json_decode(file_get_contents($tmp), true);
if (!is_array($decoded)) {
    herald_json_response(['success' => false, 'message' => 'Not a valid JSON config file'], 400);
}

$dest = sys_get_temp_dir() . '/herald_import_' . bin2hex(random_bytes(8)) . '.json';
file_put_contents($dest, json_encode($decoded));

$result = herald_run_sudo(['import-config', $dest]);
@unlink($dest);
herald_respond_from_cli($result);
