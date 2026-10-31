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
  alert("Vous êtes de nouveau en ligne !");
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

document.addEventListener("DOMContentLoaded", () => {
    const nav = document.querySelector('.navbar');
    if (nav && 'windowControlsOverlay' in navigator) {
        const { x } = navigator.windowControlsOverlay.getTitlebarAreaRect();
        if (x === 0) {
            nav.classList.add('search-controls-right');
        } else {
            nav.classList.add('search-controls-left');
        }
    } else if (nav) {
        nav.classList.add('search-controls-right');
    }
});