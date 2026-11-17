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

    // Modal de reporte: toma el destino del botón que lo abre
    var reportModal = document.getElementById("report-modal");
    if (reportModal) {
        var reportBody = reportModal.querySelector("#report-modal-body");
        var reportInitial = reportBody ? reportBody.innerHTML : "";
        reportModal.addEventListener("show.bs.modal", function (event) {
            var trigger = event.relatedTarget;
            if (reportBody && reportBody.innerHTML !== reportInitial) {
                reportBody.innerHTML = reportInitial;
                if (window.htmx) { window.htmx.process(reportBody); }
            }
            if (!trigger) { return; }
            var type = reportModal.querySelector("[data-report-type]");
            var id = reportModal.querySelector("[data-report-id]");
            if (type) { type.value = trigger.getAttribute("data-target-type") || ""; }
            if (id) { id.value = trigger.getAttribute("data-target-id") || ""; }
        });
    }

    // Notificaciones de Bootstrap
    if (window.bootstrap) {
        document.querySelectorAll("[data-app-toast]").forEach(function (el) {
            window.bootstrap.Toast.getOrCreateInstance(el, { delay: 5000 }).show();
        });
    }
})();
