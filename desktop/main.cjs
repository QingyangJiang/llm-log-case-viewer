"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const { app, BrowserWindow, ipcMain, Menu, screen, dialog } = require("electron");
const { normalizeCaseLensUrl, initialPetBounds, isTrustedPetUrl } = require("./config.cjs");

let petWindow = null;
let setupWindow = null;
let studioWindow = null;
let serverUrl = "";
let settings = {};
let saveTimer = null;
const setupFile = pathToFileURL(path.join(__dirname, "setup.html")).href;

function settingsPath() { return path.join(app.getPath("userData"), "pet-settings.json"); }
function readSettings() {
  try { return JSON.parse(fs.readFileSync(settingsPath(), "utf8")); }
  catch { return {}; }
}
function saveSettings() {
  const filename = settingsPath();
  fs.mkdirSync(path.dirname(filename), { recursive: true });
  const temp = `${filename}.tmp`;
  fs.writeFileSync(temp, JSON.stringify(settings), { mode: 0o600 });
  fs.renameSync(temp, filename);
}
function scheduleSave() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveSettings, 200);
}
function appPage(page = "/desktop-pet") { return new URL(page, `${serverUrl}/`).href; }
function isPetSender(event) {
  return petWindow && !petWindow.isDestroyed() && event.sender === petWindow.webContents && isTrustedPetUrl(event.sender.getURL(), serverUrl);
}
function stayOnSite(contents) {
  contents.on("will-navigate", (event, address) => {
    try {
      if (new URL(address).origin === serverUrl) return;
    } catch { /* Leave the current window unchanged. */ }
    event.preventDefault();
  });
  contents.setWindowOpenHandler(({ url }) => {
    try {
      const target = new URL(url);
      if (target.origin === serverUrl) {
        if (studioWindow && !studioWindow.isDestroyed()) void studioWindow.loadURL(target.href);
        return { action: "deny" };
      }
    } catch { /* Ignore unknown protocols. */ }
    return { action: "deny" };
  });
}
function openStudio(section = "wardrobe") {
  const target = appPage(`/?petStudio=${section}`);
  if (studioWindow && !studioWindow.isDestroyed()) { studioWindow.show(); studioWindow.focus(); void studioWindow.loadURL(target); return; }
  studioWindow = new BrowserWindow({
    width: 1180, height: 800, minWidth: 780, minHeight: 560,
    title: "CaseLens · 宠物工作室",
    webPreferences: { nodeIntegration: false, contextIsolation: true, sandbox: true },
  });
  stayOnSite(studioWindow.webContents);
  studioWindow.on("closed", () => { studioWindow = null; });
  void studioWindow.loadURL(target);
}
function openSetup() {
  if (setupWindow && !setupWindow.isDestroyed()) { setupWindow.focus(); return; }
  setupWindow = new BrowserWindow({
    width: 410, height: 265, resizable: false, title: "连接 CaseLens · 小镜",
    webPreferences: {
      preload: path.join(__dirname, "setup-preload.cjs"),
      nodeIntegration: false, contextIsolation: true, sandbox: true,
    },
  });
  setupWindow.webContents.on("will-navigate", (event, address) => { if (address !== setupFile) event.preventDefault(); });
  setupWindow.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  setupWindow.on("closed", () => { setupWindow = null; });
  void setupWindow.loadFile(path.join(__dirname, "setup.html"));
}
function showContextMenu() {
  Menu.buildFromTemplate([
    { label: "打开 CaseLens 衣柜", click: () => openStudio("wardrobe") },
    { label: "刷新小镜", click: () => petWindow?.reload() },
    { label: "更换服务器地址", click: openSetup },
    { type: "separator" },
    { label: "退出桌面小镜", click: () => app.quit() },
  ]).popup({ window: petWindow });
}
function openPet() {
  if (petWindow && !petWindow.isDestroyed()) { petWindow.show(); petWindow.focus(); void petWindow.loadURL(appPage()); return; }
  const display = settings.bounds ? screen.getDisplayMatching({ ...settings.bounds, width: 282, height: 330 }) : screen.getPrimaryDisplay();
  petWindow = new BrowserWindow({
    ...initialPetBounds(settings.bounds, display.workArea),
    transparent: true, frame: false, resizable: false, hasShadow: false,
    backgroundColor: "#00000000", alwaysOnTop: true,
    title: "CaseLens · 小镜",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      nodeIntegration: false, contextIsolation: true, sandbox: true,
    },
  });
  petWindow.setAlwaysOnTop(true, "floating");
  petWindow.webContents.on("will-navigate", (event, address) => { if (address !== appPage()) event.preventDefault(); });
  petWindow.webContents.setWindowOpenHandler(({ url }) => {
    try {
      const target = new URL(url);
      if (target.origin === serverUrl && target.pathname === "/") {
        openStudio(target.searchParams.get("petStudio") === "equipment" ? "equipment" : "wardrobe");
      }
    } catch { /* Ignore malformed navigation. */ }
    return { action: "deny" };
  });
  petWindow.webContents.on("context-menu", showContextMenu);
  petWindow.on("moved", () => { settings.bounds = petWindow?.getBounds(); scheduleSave(); });
  petWindow.on("closed", () => { petWindow = null; });
  petWindow.webContents.on("did-fail-load", (_event, code, _description, _url, isMainFrame) => {
    if (isMainFrame && code !== -3) {
      dialog.showErrorBox("连接 CaseLens 失败", "请检查内网地址和网络；右键小镜可更换服务器地址。");
      openSetup();
    }
  });
  void petWindow.loadURL(appPage());
}

if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on("second-instance", () => { if (petWindow) { petWindow.show(); petWindow.focus(); } else openSetup(); });
  app.whenReady().then(() => {
    settings = readSettings();
    try { serverUrl = normalizeCaseLensUrl(process.env.CASELENS_URL || settings.serverUrl || ""); }
    catch { serverUrl = ""; }
    ipcMain.handle("pet:save-server", (event, address) => {
      if (!setupWindow || event.sender !== setupWindow.webContents || event.sender.getURL() !== setupFile) throw new Error("非法设置请求");
      serverUrl = normalizeCaseLensUrl(address);
      settings.serverUrl = serverUrl;
      saveSettings();
      openPet();
      setupWindow.close();
    });
    ipcMain.on("pet:move-by", (event, dx, dy) => {
      if (!isPetSender(event) || !Number.isFinite(dx) || !Number.isFinite(dy) || Math.abs(dx) > 80 || Math.abs(dy) > 80) return;
      const [x, y] = petWindow.getPosition();
      petWindow.setPosition(Math.round(x + dx), Math.round(y + dy));
    });
    ipcMain.on("pet:open-studio", (event, section) => { if (isPetSender(event)) openStudio(section === "equipment" ? "equipment" : "wardrobe"); });
    ipcMain.on("pet:close", (event) => { if (isPetSender(event)) app.quit(); });
    if (serverUrl) openPet(); else openSetup();
  });
  app.on("activate", () => { if (serverUrl) openPet(); else openSetup(); });
  app.on("window-all-closed", () => app.quit());
  app.on("before-quit", () => { clearTimeout(saveTimer); if (settings.bounds) saveSettings(); });
}
