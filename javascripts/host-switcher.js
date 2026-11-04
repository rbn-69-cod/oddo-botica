// MediZano POS - Dynamic Host Switcher (AWS EC2 / Localhost / Custom IP)
(function () {
  var DEFAULT_HOST = "54.226.25.238";
  var OLD_HOST = "32.192.88.0";

  function getTargetHost() {
    var saved = localStorage.getItem("medizano_target_host");
    if (saved === OLD_HOST) {
      localStorage.removeItem("medizano_target_host");
      saved = null;
    }
    if (saved && saved.trim() !== "") {
      return saved.trim();
    }
    var current = window.location.hostname;
    if (current && current.trim() !== "" && current !== "0.0.0.0") {
      return current.trim();
    }
    return DEFAULT_HOST;
  }

  function setTargetHost(host) {
    if (!host || host.trim() === "") {
      localStorage.removeItem("medizano_target_host");
    } else {
      localStorage.setItem("medizano_target_host", host.trim());
    }
    updateAllLinks();
    updateWidgetUI();
  }

  function updateAllLinks() {
    var targetHost = getTargetHost();
    var isLocal = targetHost === "localhost" || targetHost === "127.0.0.1";

    var links = document.querySelectorAll("a[data-service-port], a[href*=\"localhost\"], a[href*=\"127.0.0.1\"], a[href*=\"32.192.88.0\"], a[href*=\"35.168.17.123\"]");
    links.forEach(function (link) {
      var port = link.getAttribute("data-service-port");
      var path = link.getAttribute("data-service-path") || "";

      if (port !== null) {
        var newHref;
        if (port === "80" || port === "") {
          newHref = "http://" + targetHost + (path.startsWith("/") ? path : "/" + path);
        } else {
          newHref = "http://" + targetHost + ":" + port + (path.startsWith("/") ? path : "/" + path);
        }
        link.setAttribute("href", newHref);
        var urlLabel = link.querySelector(".service-url-badge");
        if (urlLabel) {
          urlLabel.textContent = newHref;
        }
      } else {
        var href = link.getAttribute("href");
        if (!href) return;
        var updatedHref = href
          .replace(/localhost/g, targetHost)
          .replace(/127\.0\.0\.1/g, targetHost)
          .replace(/32\.192\.88\.0/g, targetHost)
          .replace(/35\.168\.17\.123/g, targetHost);
        link.setAttribute("href", updatedHref);
      }
    });

    var codeBlocks = document.querySelectorAll("code");
    codeBlocks.forEach(function (code) {
      if (code.getAttribute("data-host-updated") === targetHost) return;
      if (
        code.textContent.indexOf("localhost:") !== -1 ||
        code.textContent.indexOf("127.0.0.1:") !== -1 ||
        code.textContent.indexOf("32.192.88.0") !== -1 ||
        code.textContent.indexOf("35.168.17.123") !== -1
      ) {
        code.setAttribute("data-orig-text", code.getAttribute("data-orig-text") || code.textContent);
        var baseText = code.getAttribute("data-orig-text");
        code.textContent = baseText
          .replace(/32\.192\.88\.0/g, targetHost)
          .replace(/localhost/g, targetHost)
          .replace(/127\.0\.0\.1/g, targetHost);
        code.setAttribute("data-host-updated", targetHost);
      }
    });
  }

  function updateWidgetUI() {
    var targetHost = getTargetHost();
    var currentHost = window.location.hostname || "localhost";
    var isLocal = targetHost === "localhost" || targetHost === "127.0.0.1";

    var hostDisplay = document.getElementById("medizano-current-host-display");
    if (hostDisplay) {
      hostDisplay.textContent = targetHost;
    }

    var ipInput = document.getElementById("medizano-custom-ip-input");
    if (ipInput && document.activeElement !== ipInput) {
      ipInput.value = targetHost;
    }

    var btnAuto = document.getElementById("btn-host-auto");
    var btnLocal = document.getElementById("btn-host-local");
    if (btnAuto) {
      btnAuto.classList.toggle("active-mode", targetHost === currentHost && !isLocal);
    }
    if (btnLocal) {
      btnLocal.classList.toggle("active-mode", isLocal);
    }
  }

  function initHostSwitcher() {
    updateAllLinks();
    updateWidgetUI();

    document.addEventListener("click", function (e) {
      var target = e.target;
      if (!target) return;

      if (target.id === "btn-host-auto" || target.closest("#btn-host-auto")) {
        var host = window.location.hostname || DEFAULT_HOST;
        setTargetHost(host);
        showToast("IP detectada automáticamente: " + host);
      } else if (target.id === "btn-host-local" || target.closest("#btn-host-local")) {
        setTargetHost("localhost");
        showToast("Entorno cambiado a: localhost (127.0.0.1)");
      } else if (target.id === "btn-host-save" || target.closest("#btn-host-save")) {
        var input = document.getElementById("medizano-custom-ip-input");
        if (input && input.value.trim() !== "") {
          var cleaned = input.value.trim().replace(/^https?:\/\//, "").replace(/\/.*$/, "");
          setTargetHost(cleaned);
          showToast("IP personalizada guardada: " + cleaned);
        } else {
          showToast("Ingresa una IP válida antes de guardar");
        }
      }
    });

    var customInput = document.getElementById("medizano-custom-ip-input");
    if (customInput) {
      customInput.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
          var saveBtn = document.getElementById("btn-host-save");
          if (saveBtn) saveBtn.click();
        }
      });
    }
  }

  function showToast(msg) {
    var toast = document.getElementById("medizano-host-toast");
    if (!toast) {
      toast = document.createElement("div");
      toast.id = "medizano-host-toast";
      toast.style.cssText = "position:fixed;bottom:24px;right:24px;background:#0d9488;color:#fff;padding:12px 20px;border-radius:8px;font-size:14px;font-weight:600;box-shadow:0 4px 12px rgba(0,0,0,0.25);z-index:99999;transition:opacity 0.3s;opacity:0;pointer-events:none;";
      document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.style.opacity = "1";
    setTimeout(function () {
      toast.style.opacity = "0";
    }, 2800);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initHostSwitcher);
  } else {
    initHostSwitcher();
  }

  if (typeof document$ !== "undefined") {
    document$.subscribe(function () {
      initHostSwitcher();
    });
  }
})();
