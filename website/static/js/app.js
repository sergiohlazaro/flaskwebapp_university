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

    // Confirmación de acciones destructivas (sin JS inline). Los formularios con
    // hx-confirm los confirma htmx; aquí solo los que se envían de forma normal.
    document.addEventListener("submit", function (event) {
        var form = event.target;
        if (!form || !form.getAttribute || form.hasAttribute("hx-confirm")) { return; }
        var message = form.getAttribute("data-confirm");
        if (message && !window.confirm(message)) {
            event.preventDefault();
        }
    });

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

    // Fallos de htmx (403/404/5xx): aviso genérico
    document.body.addEventListener("htmx:responseError", function () {
        var container = document.querySelector(".app-toasts");
        if (!container) {
            container = document.createElement("div");
            container.className = "toast-container position-fixed top-0 end-0 p-3 app-toasts";
            document.body.appendChild(container);
        }
        var toast = document.createElement("div");
        toast.className = "toast align-items-center border-0 text-bg-danger";
        toast.setAttribute("role", "alert");
        toast.setAttribute("aria-live", "assertive");
        toast.setAttribute("aria-atomic", "true");
        var row = document.createElement("div");
        row.className = "d-flex";
        var text = document.createElement("div");
        text.className = "toast-body";
        text.textContent = "No se pudo completar la acción.";
        row.appendChild(text);
        toast.appendChild(row);
        container.appendChild(toast);
        if (window.bootstrap) {
            window.bootstrap.Toast.getOrCreateInstance(toast, { delay: 5000 }).show();
        }
    });

    // Notificaciones de Bootstrap
    if (window.bootstrap) {
        document.querySelectorAll("[data-app-toast]").forEach(function (el) {
            window.bootstrap.Toast.getOrCreateInstance(el, { delay: 5000 }).show();
        });
    }
})();
