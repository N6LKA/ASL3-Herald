<?php
// asl3-herald.php
//
// Installed directly into Supermon's own directory (not /asl3-herald/) so
// it can use Supermon's real login session. Supermon's session cookie is
// named "supermon61" (set by session.inc's session_start(['name' => ...])),
// a different cookie from PHP's default PHPSESSID — a page living outside
// Supermon's own directory calling plain session_start() reads the wrong
// session entirely, which is why an earlier version of this page always
// showed Access Denied regardless of actual login state.
//
// session.inc/header.inc/footer.inc are Supermon's own real files, included
// unmodified — this gives real Supermon chrome (nav, login dialog) for free
// and means login detection always matches whatever Supermon itself does.
include("session.inc");
include("header.inc");
?>

<?php if (isset($_SESSION['sm61loggedin']) && $_SESSION['sm61loggedin'] === true): ?>
    <?php include __DIR__ . '/../asl3-herald/herald-ui-fragment.php'; ?>
    <script src="/asl3-herald/herald-ui.js"></script>
<?php else: ?>
    <p style="text-align:center; margin-top:40px;">
        Please log in (top of page) to manage ASL3 Herald announcements.
    </p>
<?php endif; ?>

<?php include "footer.inc"; ?>
