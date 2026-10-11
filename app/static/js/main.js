// Hospital Management System - Master Frontend & Dynamic UI Interactions

document.addEventListener("DOMContentLoaded", function () {
  "use strict";

  // 1. Dark Mode Theme Switcher & LocalStorage Persistence
  const themeToggleBtn = document.getElementById("themeToggleBtn");
  const themeIcon = document.getElementById("themeIcon");

  function applyTheme(theme) {
    if (theme === "dark") {
      document.documentElement.setAttribute("data-theme", "dark");
      if (themeIcon) {
        themeIcon.classList.remove("bi-moon-stars");
        themeIcon.classList.add("bi-sun");
      }
    } else {
      document.documentElement.removeAttribute("data-theme");
      if (themeIcon) {
        themeIcon.classList.remove("bi-sun");
        themeIcon.classList.add("bi-moon-stars");
      }
    }
  }

  // Initialize theme from storage or system preference
  const savedTheme = localStorage.getItem("hms-theme") || "light";
  applyTheme(savedTheme);

  if (themeToggleBtn) {
    themeToggleBtn.addEventListener("click", function () {
      const currentTheme = document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
      const newTheme = currentTheme === "dark" ? "light" : "dark";
      localStorage.setItem("hms-theme", newTheme);
      applyTheme(newTheme);

      // Re-render chart text colors if Chart is defined
      if (typeof Chart !== "undefined") {
        Chart.instances && Object.values(Chart.instances).forEach(function(inst) {
          inst.update();
        });
      }
    });
  }

  // 2. Real-time Digital Dashboard Clock
  const clockEl = document.getElementById("liveDashboardClock");
  if (clockEl) {
    function updateClock() {
      const now = new Date();
      const hours = String(now.getHours()).padStart(2, "0");
      const minutes = String(now.getMinutes()).padStart(2, "0");
      const seconds = String(now.getSeconds()).padStart(2, "0");
      clockEl.textContent = `${hours}:${minutes}:${seconds}`;
    }
    updateClock();
    setInterval(updateClock, 1000);
  }

  // 3. Celebration Confetti Burst on Success Alerts
  const hasSuccessAlert = document.querySelector(".alert-success");
  if (hasSuccessAlert && typeof confetti === "function") {
    try {
      confetti({
        particleCount: 40,
        spread: 60,
        origin: { y: 0.15 },
        colors: ["#0D9488", "#10B981", "#3B82F6", "#F59E0B"],
        disableForReducedMotion: true
      });
    } catch (e) {
      // Graceful fallback if blocked
    }
  }

  // 4. Password show/hide toggle functionality
  const toggleButtons = document.querySelectorAll(".toggle-password-visibility");
  toggleButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      const targetId = button.getAttribute("data-target");
      const passwordInput = document.getElementById(targetId);
      const icon = button.querySelector("i");

      if (passwordInput) {
        if (passwordInput.type === "password") {
          passwordInput.type = "text";
          if (icon) {
            icon.classList.remove("bi-eye");
            icon.classList.add("bi-eye-slash");
          }
          button.setAttribute("aria-label", "Hide password");
        } else {
          passwordInput.type = "password";
          if (icon) {
            icon.classList.remove("bi-eye-slash");
            icon.classList.add("bi-eye");
          }
          button.setAttribute("aria-label", "Show password");
        }
        passwordInput.focus();
      }
    });
  });

  // 5. Mobile sidebar drawer toggle functionality
  const sidebarToggle = document.getElementById("sidebarToggle");
  const sidebar = document.getElementById("sidebar-wrapper");
  const backdrop = document.querySelector(".sidebar-backdrop");

  function closeSidebar() {
    if (sidebar) sidebar.classList.remove("show");
    if (backdrop) backdrop.classList.remove("show");
  }

  function openSidebar() {
    if (sidebar) sidebar.classList.add("show");
    if (backdrop) backdrop.classList.add("show");
  }

  if (sidebarToggle && sidebar) {
    sidebarToggle.addEventListener("click", function () {
      if (sidebar.classList.contains("show")) {
        closeSidebar();
      } else {
        openSidebar();
      }
    });
  }

  if (backdrop) {
    backdrop.addEventListener("click", closeSidebar);
  }

  // 6. Global Keyboard Shortcut (Ctrl+K / Cmd+K for Quick Navigation, ESC to close)
  const quickNavModalEl = document.getElementById("quickNavModal");
  let quickNavModal = null;
  if (quickNavModalEl && typeof bootstrap !== "undefined") {
    quickNavModal = new bootstrap.Modal(quickNavModalEl);
  }

  document.addEventListener("keydown", function (e) {
    // Ctrl+K or Cmd+K: Open Quick Command Palette
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      if (quickNavModal) {
        quickNavModal.show();
      }
    }

    // Escape: Close Mobile Sidebar or Modals
    if (e.key === "Escape") {
      closeSidebar();
    }
  });

  // Focus and filter in Quick Nav modal
  if (quickNavModalEl) {
    quickNavModalEl.addEventListener("shown.bs.modal", function () {
      const input = document.getElementById("quickNavInput");
      if (input) {
        input.value = "";
        input.focus();
        filterQuickNav("");
      }
    });

    const quickNavInput = document.getElementById("quickNavInput");
    if (quickNavInput) {
      quickNavInput.addEventListener("input", function () {
        filterQuickNav(this.value.trim().toLowerCase());
      });
    }
  }

  function filterQuickNav(term) {
    const list = document.getElementById("quickNavList");
    if (!list) return;
    const items = list.querySelectorAll(".list-group-item");
    items.forEach(function (item) {
      const text = item.textContent.toLowerCase();
      if (!term || text.includes(term)) {
        item.style.display = "flex";
      } else {
        item.style.display = "none";
      }
    });
  }

  // 7. Auto-dismiss flash notifications smoothly after 4.5 seconds
  const flashAlerts = document.querySelectorAll(".flash-messages-container .alert");
  flashAlerts.forEach(function (alert) {
    setTimeout(function () {
      alert.style.transition = "opacity 0.4s ease, transform 0.4s ease";
      alert.style.opacity = "0";
      alert.style.transform = "translateY(-8px)";
      setTimeout(function () {
        if (alert.parentNode) {
          alert.remove();
        }
      }, 400);
    }, 4500);
  });

  // 8. Bootstrap Tooltip Initialization
  if (typeof bootstrap !== "undefined" && bootstrap.Tooltip) {
    const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    tooltipTriggerList.forEach(function (el) {
      new bootstrap.Tooltip(el);
    });
  }
});
