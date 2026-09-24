"use strict";

const { contextBridge, ipcRenderer } = require("electron");

// Only these window actions are exposed to the remote CaseLens page.
contextBridge.exposeInMainWorld("caseLensDesktop", {
  moveBy: (dx, dy) => ipcRenderer.send("pet:move-by", dx, dy),
  openStudio: () => ipcRenderer.send("pet:open-studio"),
  close: () => ipcRenderer.send("pet:close"),
});
