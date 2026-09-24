"use strict";

const { contextBridge, ipcRenderer } = require("electron");
contextBridge.exposeInMainWorld("caseLensSetup", {
  save: (address) => ipcRenderer.invoke("pet:save-server", address),
});
