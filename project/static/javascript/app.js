function showOfflineNotification() {
  if ("serviceWorker" in navigator && "Notification" in window) {
    Notification.requestPermission().then((permission) => {
      if (permission === "granted") {
        new Notification("📶 Vous êtes hors ligne", {
          body: "Certaines fonctionnalités peuvent être limitées.",
          icon: "/static/image/favicon-192x192.png"
        });
      }
    });
  }
}

// Listen for connection loss
window.addEventListener("offline", () => {
  console.log("⚠️ Perte de connexion !");
  showOfflineNotification();
});

// Optionally, notify when back online
window.addEventListener("online", () => {
  console.log("✅ Connexion rétablie !");
});

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js", { scope: "/" })
      .then(async (reg) => {
        console.log("[Service Worker] Registered", reg);

        // Periodic Background Sync (Android Chrome / Edge)
        if ("periodicSync" in reg) {
          try {
            const status = await navigator.permissions.query({ name: "periodic-background-sync" });
            if (status.state === "granted") {
              await reg.periodicSync.register("refresh-library", {
                minInterval: 24 * 60 * 60 * 1000
              });
              console.log("[SW] Periodic background sync registered.");
            }
          } catch (err) {
            console.log("[SW] Periodic sync not supported:", err);
          }
        }
      })
      .catch((err) => console.log("[Service Worker] Registration failed", err));
  });
}

// PWA Install Prompt Global Handler
window.deferredPrompt = null;
window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    window.deferredPrompt = e;
    // Notify other scripts that the app is installable
    window.dispatchEvent(new Event('app-installable'));
});

// Window Controls Overlay & Navbar alignment (Windows PWA titlebar)
function updateNavbarControls() {
    const nav = document.querySelector('.navbar');
    if (nav && 'windowControlsOverlay' in navigator) {
        const { x } = navigator.windowControlsOverlay.getTitlebarAreaRect();
        if (x === 0) {
            nav.classList.add('search-controls-right');
            nav.classList.remove('search-controls-left');
        } else {
            nav.classList.add('search-controls-left');
            nav.classList.remove('search-controls-right');
        }
    } else if (nav) {
        nav.classList.add('search-controls-right');
    }
}

document.addEventListener("DOMContentLoaded", updateNavbarControls);
document.addEventListener("htmx:load", updateNavbarControls);
if (document.readyState !== "loading") {
    updateNavbarControls();
}

// Non-blocking Toast notification for HTMX network errors
document.addEventListener("htmx:sendError", () => {
    console.warn("⚠️ [HTMX] Erreur de transmission réseau / hors ligne.");
    if (!document.getElementById("htmx-network-toast")) {
        const toast = document.createElement("div");
        toast.id = "htmx-network-toast";
        toast.className = "notification is-warning is-light";
        toast.style.cssText = "position: fixed; bottom: 20px; right: 20px; z-index: 10000; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); max-width: 350px;";
        toast.innerHTML = '<button class="delete"></button><strong>Connexion interrompue</strong><br>Impossible d\'effectuer l\'action. Vérifiez votre réseau.';
        toast.querySelector(".delete").addEventListener("click", () => toast.remove());
        document.body.appendChild(toast);
        setTimeout(() => { if (toast.parentNode) toast.remove(); }, 6000);
    }
});
