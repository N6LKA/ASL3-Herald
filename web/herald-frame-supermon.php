<?php
// herald-frame-supermon.php
//
// Auth-gated entry point for embedding asl3-herald's web UI inside Supermon 7.
// Supermon stores login state in $_SESSION['sm61loggedin']. This file runs
// as its own request (e.g. linked from Supermon's menu or embedded in an
// iframe), so it starts its own session and reads the same session cookie
// Supermon already set — proven to work by other Supermon add-ons that live
// in a separate directory under the same Apache vhost.

session_start();

if (!isset($_SESSION['sm61loggedin']) || $_SESSION['sm61loggedin'] !== true) {
    http_response_code(403);
    echo "<h2 style='text-align:center; color:red; margin-top:80px;'>Access Denied</h2>";
    echo "<p style='text-align:center;'>You must be logged into Supermon to view this page.</p>";
    echo "<p style='text-align:center;'><a href='/supermon/link.php'>&larr; Go to Supermon</a></p>";
    exit;
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ASL3 Herald</title>
</head>
<body style="margin:0; padding:16px; background:#f4f4f4;">
<?php include __DIR__ . '/herald-ui.inc'; ?>
</body>
</html>
