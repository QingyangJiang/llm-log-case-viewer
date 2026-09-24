"use strict";

function normalizeCaseLensUrl(input) {
  if (typeof input !== "string") throw new Error("请输入 CaseLens 的完整地址");
  let url;
  try { url = new URL(input.trim()); } catch { throw new Error("请输入 http:// 或 https:// 开头的 CaseLens 地址"); }
  if (!["http:", "https:"].includes(url.protocol) || !url.hostname || url.username || url.password || url.search || url.hash || url.pathname !== "/") {
    throw new Error("请输入 CaseLens 首页地址，例如 http://内网IP:8080；不要附带账号密码或路径");
  }
  return url.origin;
}

function isTrustedPetUrl(address, serverUrl) {
  try {
    const url = new URL(address);
    return url.origin === serverUrl && url.pathname.replace(/\/+$/, "") === "/desktop-pet";
  } catch { return false; }
}

function initialPetBounds(saved, workArea, width = 282, height = 330) {
  const x = Number.isInteger(saved?.x) ? saved.x : workArea.x + workArea.width - width - 24;
  const y = Number.isInteger(saved?.y) ? saved.y : workArea.y + workArea.height - height - 28;
  return {
    width, height,
    x: Math.max(workArea.x, Math.min(x, workArea.x + workArea.width - width)),
    y: Math.max(workArea.y, Math.min(y, workArea.y + workArea.height - height)),
  };
}

module.exports = { normalizeCaseLensUrl, initialPetBounds, isTrustedPetUrl };
