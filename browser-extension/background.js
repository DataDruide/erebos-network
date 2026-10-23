const TUNNEL_STARTED_KEY = "tunnelStarted";

// .erebos- und .onion-Adressen erkennen und den Tunnel starten
browser.webRequest.onBeforeRequest.addListener(
  async (details) => {
    const url = details.url;
    const isErebos = url.includes(".erebos");
    const isOnion = url.includes(".onion");
    if (!isErebos && !isOnion) return {};

    const data = await browser.storage.local.get(TUNNEL_STARTED_KEY);
    if (data[TUNNEL_STARTED_KEY]) return {};

    await browser.storage.local.set({ pendingUrl: url });
    return { redirectUrl: browser.runtime.getURL("warning.html") };
  },
  { urls: ["<all_urls>"] },
  ["blocking"]
);

browser.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "startTunnel") {
    const port = browser.runtime.connectNative("erebos_tunnel_starter");
    port.onMessage.addListener(async (response) => {
      if (response.status === "ok") {
        await browser.storage.local.set({ [TUNNEL_STARTED_KEY]: true });
        const { pendingUrl } = await browser.storage.local.get("pendingUrl");
        if (pendingUrl) {
          await browser.storage.local.remove("pendingUrl");
          browser.tabs.create({ url: pendingUrl });
        }
        sendResponse({ success: true });
      } else {
        sendResponse({ success: false, error: response.error });
      }
    });
    port.postMessage({ command: "start" });
    return true;
  }
  if (message.action === "cancel") {
    browser.storage.local.remove("pendingUrl");
    sendResponse({ success: true });
    return true;
  }
});
