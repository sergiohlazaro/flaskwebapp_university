(function () {
    "use strict";

    // Banner de cookies
    var banner = document.querySelector("[data-cookie-banner]");
    var accept = document.querySelector("[data-accept-cookies]");
    if (banner && accept) {
        accept.addEventListener("click", function () {
            document.cookie = "cookies_accepted=true; path=/; max-age=31536000; SameSite=Lax";
            banner.hidden = true;
        });
    }

    // CSRF para htmx
    var meta = document.querySelector('meta[name="csrf-token"]');
    var csrfToken = meta ? meta.getAttribute("content") : "";
    document.body.addEventListener("htmx:configRequest", function (event) {
        if (csrfToken) {
            event.detail.headers["X-CSRFToken"] = csrfToken;
        }
    });

    // Notificaciones de Bootstrap
    if (window.bootstrap) {
        document.querySelectorAll("[data-app-toast]").forEach(function (el) {
            window.bootstrap.Toast.getOrCreateInstance(el, { delay: 5000 }).show();
        });
    }
})();
