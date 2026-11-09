// Sauvegarde l'URL courante pour restaurer la navigation après une coupure réseau
if (typeof window !== "undefined" && window.location && !window.location.pathname.includes("/offline")) {
  try {
    sessionStorage.setItem("last_visited_page", window.location.href);
  } catch (e) {
    // Mode navigation privée restreint
  }
}

function handleOfflineRedirect() {
  if (typeof window !== "undefined" && window.location) {
    if (!window.location.pathname.includes("/offline")) {
      try {
        sessionStorage.setItem("last_visited_page", window.location.href);
      } catch (e) {}
      window.location.href = "/offline";
    }
  }
}

// Redirection directe vers /offline en cas de perte de connexion
window.addEventListener("offline", () => {
  console.log("⚠️ Perte de connexion, redirection vers /offline...");
  handleOfflineRedirect();
});

// En cas de reconnexion
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

// Redirection immédiate vers /offline lors d'une erreur réseau HTMX
document.addEventListener("htmx:sendError", () => {
    console.warn("⚠️ [HTMX] Erreur de transmission réseau / hors ligne, redirection vers /offline...");
    handleOfflineRedirect();
});
