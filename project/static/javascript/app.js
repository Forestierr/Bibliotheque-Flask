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
    navigator.serviceWorker.register("/sw.js")
      .then((reg) => console.log("[Service Worker] Registered", reg))
      .catch((err) => console.log("[Service Worker] Registration failed", err));
  });
}

if ('windowControlsOverlay' in navigator) {
  const { x } = navigator.windowControlsOverlay.getTitlebarAreaRect();
  console.log(x)
  // Window controls are on the right (like on Windows).
  // Chrome menu is left of the window controls.
  // [ windowControlsOverlay___________________ […] [_] [■] [X] ]
  if (x === 0) {
    nav.classList.add('search-controls-right');
  }
  // Window controls are on the left (like on macOS).
  // Chrome menu is right of the window controls overlay.
  // [ [X] [_] [■] ___________________windowControlsOverlay [⋮] ]
  else {
    div.classList.add('search-controls-left');
  }
} else {
  // When running in a non-supporting browser tab.
  div.classList.add('search-controls-right');
}