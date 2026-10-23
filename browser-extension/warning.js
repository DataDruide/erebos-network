document.getElementById("btn-start").addEventListener("click", async () => {
  const status = document.getElementById("status");
  status.textContent = "Tunnel wird gestartet…";
  const response = await browser.runtime.sendMessage({ action: "startTunnel" });
  if (response && response.success) {
    status.textContent = "Tunnel läuft.";
    window.close();
  } else {
    status.textContent = "Fehler: " + (response ? response.error : "Unbekannt");
  }
});
document.getElementById("btn-cancel").addEventListener("click", () => {
  browser.runtime.sendMessage({ action: "cancel" });
  window.close();
});
