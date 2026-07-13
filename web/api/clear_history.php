<?php
require __DIR__ . '/../herald-common.php';
$result = herald_run_sudo(['clear-history']);
herald_respond_from_cli($result);
