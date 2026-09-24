/** Export the actual wardrobe DOM, including its CSS artwork, as a Codex v1 sprite sheet. */
const CELL_WIDTH = 192;
const CELL_HEIGHT = 208;
const COLUMNS = 8;
const ROWS = 9;
export const CODEX_SHEET_WIDTH = CELL_WIDTH * COLUMNS;
export const CODEX_SHEET_HEIGHT = CELL_HEIGHT * ROWS;
// Idle, run right, run left, wave, jump, failed, waiting, working, review.
export const CODEX_FRAME_COUNTS = [6, 8, 8, 4, 5, 8, 6, 6, 6] as const;

function copyRenderedStyle(original: Element, copy: Element, pseudoRules: string[], index: { value: number }) {
  const style = window.getComputedStyle(original);
  const target = (copy as HTMLElement | SVGElement).style;
  for (const property of style) target.setProperty(property, style.getPropertyValue(property), style.getPropertyPriority(property));
  // CSS animations must not advance between the snapshot and rasterization.
  target.setProperty("animation", "none", "important");
  target.setProperty("transition", "none", "important");
  for (const pseudo of ["::before", "::after"]) {
    const computed = window.getComputedStyle(original, pseudo);
    if (computed.content === "none" || computed.content === "normal") continue;
    const marker = String(++index.value);
    copy.setAttribute(`data-codex-${pseudo.slice(2)}`, marker);
    const rules: string[] = [];
    for (const property of computed) rules.push(`${property}:${computed.getPropertyValue(property)} !important;`);
    rules.push("animation:none !important;transition:none !important;");
    pseudoRules.push(`[data-codex-${pseudo.slice(2)}="${marker}"]${pseudo}{${rules.join("")}}`);
  }
  const originalChildren = original.children;
  const copiedChildren = copy.children;
  for (let child = 0; child < originalChildren.length; child++) {
    copyRenderedStyle(originalChildren[child], copiedChildren[child], pseudoRules, index);
  }
}

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("无法绘制当前小镜穿搭，请在桌面浏览器重试"));
    image.src = url;
  });
}

/** Rasterize the exact displayed SVG, CSS creature, shoes, accessories and equipment. */
export async function capturePetLook(creature: HTMLElement): Promise<HTMLImageElement> {
  const clone = creature.cloneNode(true) as HTMLElement;
  const pseudoRules: string[] = [];
  copyRenderedStyle(creature, clone, pseudoRules, { value: 0 });
  const xmlns = "http://www.w3.org/1999/xhtml";
  const wrapper = document.createElementNS(xmlns, "div");
  wrapper.setAttribute("style", "position:relative;width:100px;height:104px;overflow:visible");
  const rules = document.createElementNS(xmlns, "style");
  rules.textContent = pseudoRules.join("\n");
  wrapper.appendChild(rules);
  clone.style.setProperty("left", "33px", "important");
  clone.style.setProperty("top", "33px", "important");
  clone.style.setProperty("transform", "none", "important");
  wrapper.appendChild(clone);
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${CELL_WIDTH}" height="${CELL_HEIGHT}" viewBox="0 0 100 104"><foreignObject width="100" height="104">${new XMLSerializer().serializeToString(wrapper)}</foreignObject></svg>`;
  const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml;charset=utf-8" }));
  try {
    const image = await loadImage(url);
    await image.decode();
    return image;
  } finally { URL.revokeObjectURL(url); }
}

export function drawCodexSheet(image: CanvasImageSource): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = CODEX_SHEET_WIDTH;
  canvas.height = CODEX_SHEET_HEIGHT;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("浏览器不支持画布导出");
  // A fresh transparent canvas leaves the unused cells genuinely empty.
  for (let row = 0; row < ROWS; row++) {
    const count = CODEX_FRAME_COUNTS[row];
    for (let frame = 0; frame < count; frame++) {
      const phase = 2 * Math.PI * frame / count;
      const x = (frame + .5) * CELL_WIDTH;
      const y = (row + .5) * CELL_HEIGHT;
      context.save();
      context.translate(x, y);
      if (row === 0) context.translate(0, Math.round(Math.sin(phase) * 2));
      if (row === 1 || row === 2) {
        context.translate((row === 1 ? 1 : -1) * Math.round(Math.sin(phase) * 9), Math.abs(Math.sin(phase)) * -5);
        if (row === 2) context.scale(-1, 1);
      }
      if (row === 3) context.rotate(Math.sin(phase) * .095);
      if (row === 4) context.translate(0, -Math.round(28 * Math.max(0, Math.sin(Math.PI * frame / (count - 1)))));
      if (row === 5) context.rotate(-.17 - Math.sin(phase) * .05);
      if (row === 6) context.translate(0, Math.round(Math.sin(phase) * 1));
      if (row === 7) context.rotate(Math.sin(phase) * .025);
      if (row === 8) context.rotate(Math.sin(phase) * .045);
      context.drawImage(image, -CELL_WIDTH / 2, -CELL_HEIGHT / 2, CELL_WIDTH, CELL_HEIGHT);
      context.restore();
    }
  }
  return canvas;
}

export async function exportCodexSprite(creature: HTMLElement): Promise<Blob> {
  const image = await capturePetLook(creature);
  const canvas = drawCodexSheet(image);
  return new Promise((resolve, reject) => canvas.toBlob((blob) => blob ? resolve(blob) : reject(new Error("精灵图生成失败")), "image/png"));
}

export function downloadCodexSprite(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
