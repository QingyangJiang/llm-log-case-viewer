"use client";

import { useId } from "react";
import { RouteRegalia } from "./pet-route-regalia";
import { RouteProgress } from "./pet-route-progress";

export const ILLUSTRATED_ROUTES = {
  eva: { light: "#c0a3ff", base: "#8660d1", dark: "#302846", accent: "#c7fc75", soft: "#eee5ff", caption: "紫晶装甲 · 荧光核心" },
  blade_soul: { light: "#ffffff", base: "#d3f1ef", dark: "#326c78", accent: "#83ddd1", soft: "#e5fbf7", caption: "灵族灵剑士 · 青玉飞剑" },
  dnf: { light: "#ac869f", base: "#69516f", dark: "#372c49", accent: "#ffc776", soft: "#fff0df", caption: "鬼剑士 · 鬼手与锁链" },
  nba: { light: "#ffe6b3", base: "#e9ac67", dark: "#614538", accent: "#f28d50", soft: "#fff2d8", caption: "奶橘球星 · 冠军球衣" },
  honor: { light: "#fff7fa", base: "#e3c6df", dark: "#755f86", accent: "#c5a4df", soft: "#f7edf7", caption: "梦奇灵感 · 绒耳与梦泡" },
  valorant: { light: "#f3faff", base: "#bfdadf", dark: "#304b5e", accent: "#72decf", soft: "#e6fbf7", caption: "捷风灵感 · 白发与飞刃" },
  lol: { light: "#ffecdc", base: "#edc6b8", dark: "#684b64", accent: "#9edeea", soft: "#f3edf6", caption: "阿狸灵感 · 灵珠与狐火" },
  nexus: { light: "#9285ca", base: "#504d88", dark: "#2a2b53", accent: "#d0bcff", soft: "#ede7ff", caption: "星河绒羽 · 月相之环" },
} as const;

export type IllustratedRoute = keyof typeof ILLUSTRATED_ROUTES;

export function isIllustratedRoute(path: string): path is IllustratedRoute {
  return Object.prototype.hasOwnProperty.call(ILLUSTRATED_ROUTES, path);
}

function Spark({ x, y, size = 4, color = "#fff6ce" }: { x: number; y: number; size?: number; color?: string }) {
  return <path d={`M${x} ${y - size}q0 ${size} ${size} ${size}q-${size} 0 -${size} ${size}q0 -${size} -${size} -${size}q${size} 0 ${size} -${size}`} fill={color} stroke="none" />;
}

function Face({ ink, iris, y = 75, fierce = false, human = false }: { ink: string; iris: string; y?: number; fierce?: boolean; human?: boolean }) {
  return <g className="route-face">
    <ellipse cx="60" cy={y + 10} rx="6" ry="3" fill="#eea7a0" opacity=".44" stroke="none" />
    <ellipse cx="100" cy={y + 10} rx="6" ry="3" fill="#eea7a0" opacity=".44" stroke="none" />
    <g className="route-eyes" fill={ink} stroke="none">
      <ellipse cx="65" cy={y} rx="5" ry="6.8" /><ellipse cx="95" cy={y} rx="5" ry="6.8" />
      <ellipse cx="65.5" cy={y + 2.5} rx="2.9" ry="3.2" fill={iris} /><ellipse cx="95.5" cy={y + 2.5} rx="2.9" ry="3.2" fill={iris} />
      <circle cx="63.5" cy={y - 2.5} r="1.9" fill="white" /><circle cx="93.5" cy={y - 2.5} r="1.9" fill="white" />
    </g>
    {fierce ? <path d={`M59 ${y - 9}l11 3m20 0 11-3`} fill="none" stroke={ink} strokeWidth="2.3" /> : null}
    {!human ? <><path d={`M77 ${y + 9}q3-2 6 0l-3 3Z`} fill={ink} stroke="none" />
    <path d={`M80 ${y + 12}q-3 5-6 1m6-1q3 5 6 1`} fill="none" stroke={ink} strokeWidth="1.6" /></> : <path d={`M77 ${y + 13}q3 3 7-1`} fill="none" stroke={ink} strokeWidth="1.5" />}
  </g>;
}

/** Complete vector silhouettes; the same artwork is used at every display size. */
export function PetRouteArt({ path, stage = 1 }: { path: IllustratedRoute; stage?: number }) {
  const uid = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const palette = ILLUSTRATED_ROUTES[path];
  const paint = (name: string) => `url(#pet-${uid}-${name})`;
  const body = paint("body");
  const metal = paint("metal");
  const ink = palette.dark;
  return <svg className={`pet-route-illustration route-art-${path}`} viewBox="0 0 160 160" fill="none" aria-hidden="true" focusable="false">
    <defs>
      <linearGradient id={`pet-${uid}-body`} x1="50" y1="36" x2="113" y2="128" gradientUnits="userSpaceOnUse"><stop stopColor={palette.light} /><stop offset="1" stopColor={palette.base} /></linearGradient>
      <linearGradient id={`pet-${uid}-metal`} x1="50" y1="35" x2="101" y2="126" gradientUnits="userSpaceOnUse"><stop stopColor="#fff2c9" /><stop offset=".46" stopColor="#e9bf7c" /><stop offset="1" stopColor="#bc8850" /></linearGradient>
      <linearGradient id={`pet-${uid}-gem`} x1="65" y1="30" x2="94" y2="104" gradientUnits="userSpaceOnUse"><stop stopColor="#f5ffff" /><stop offset=".4" stopColor={palette.accent} /><stop offset="1" stopColor={palette.base} /></linearGradient>
      <radialGradient id={`pet-${uid}-halo`}><stop stopColor={palette.accent} stopOpacity=".2" /><stop offset="1" stopColor={palette.accent} stopOpacity="0" /></radialGradient>
    </defs>
    <ellipse cx="80" cy="140" rx="33" ry="5" fill={ink} opacity=".12" />
    <RouteRegalia path={path} stage={stage} />
    <RouteProgress path={path} stage={stage} />
    <g className="route-familiar" stroke={ink} strokeWidth="1.9" strokeLinejoin="round" strokeLinecap="round">
      {path === "eva" ? <>
        <path d="M111 119c26 14 34-13 21-19" stroke="#5a487c" strokeWidth="5" /><path d="m130 99 6 1-1 8-6-2Z" fill="#e9ac66" />
        <g className="route-floating" transform={stage >= 3 ? undefined : "translate(12 14) scale(.85)"}><path d="M42 75 30 41l-9 9 6 42 13 7M118 75l12-34 9 9-6 42-13 7" fill={body} /><path d="m29 49 5 14m97-14-5 14" stroke="#c7fc75" strokeWidth="4" /></g>
        <path d="m59 109-5 22q8 8 19 0l2-15m11-7 2 22q11 8 19 0l-5-23" fill={body} /><path d="m56 131 16-2m18 0 15 2" stroke="#bbf36c" strokeWidth="3" />
        <path d="M54 98q26-16 52 0l-4 25-22 9-22-9Z" fill={body} /><path d="m62 104 18 8 18-8-5 17H67Z" fill="#302846" /><path className="route-personal-accent" d="m72 112 8-5 8 5-8 8Z" fill="#f4b369" strokeWidth="1.3" />
        <path d="m53 92-14 4-5 19 11 7 14-16m48-14 14 4 5 19-11 7-14-16" fill={body} /><path d="m38 111 8 4m68 0 8-4" stroke="#c7fc75" strokeWidth="3" />
        <path d="m46 57 5-18 21 9h16l21-9 5 18 2 24-14 17H58L44 81Z" fill={body} />
        <path d="m52 60 19 4 9-8 9 8 19-4-5 24-23 9-23-9Z" fill="#352d4d" />
        <path d="m53 69 20 4-5 7-12-4Zm54 0-20 4 5 7 12-4Z" fill="#c7fc75" stroke="none" /><path d="m57 70 10 2m26 0 10-2" stroke="#f4ffe1" strokeWidth="1.6" />
        <path d="m73 56 7-29 7 29-7 9Z" fill={metal} /><path d="m75 88 5-9 5 9-5 6Z" fill="#9c7bd6" strokeWidth="1.3" /><path d="m50 51 8 3m44 0 8-3" stroke="#c7fc75" strokeWidth="3" />
        <path d="m53 84 5 9m49-9-5 9" stroke="#bba2ee" strokeWidth="3" />
      </> : null}
      {path === "blade_soul" ? <g stroke="#557f86" strokeWidth="1.7">
        <path d="M99 117c25 19 48-1 39-30-5 18-17 11-22 7 4 15-3 16-17 23Z" fill={body} /><path d="M115 119q20-1 19-20" stroke="#b0ded5" />
        <path d="M57 99q23-14 46 0l5 31q-28 13-56 0Z" fill="#fcfcf5" /><path d="m65 99 15 14 15-14-10 32H75Z" fill="#9dd5ce" /><path d="M61 116q19 6 38 0" stroke="#c6a765" strokeWidth="3" />
        <ellipse cx="64" cy="134" rx="9" ry="5" fill="#f3fcf8" /><ellipse cx="96" cy="134" rx="9" ry="5" fill="#f3fcf8" />
        <path d="M53 54Q36 44 40 21q20 4 28 27m24 0q8-23 28-27 4 23-13 33" fill={body} /><path d="M47 33q0 10 11 17m44 0q11-7 11-17" stroke="#d5b9ba" strokeWidth="5" />
        <path d="M47 66q0-25 33-25t33 25l5 17-8-1 3 10q-33 21-66 0l3-10-8 1Z" fill={body} />
        <path d="M57 79q9-3 23 4 14-7 23-4l2 12q-25 18-50 0Z" fill="#fffdf6" stroke="none" />
        <path d="M65 46q9-9 18-6l-4 9 10-4-4 11" stroke="#badcd7" fill="#fffefa" />
        <Face ink="#3b626b" iris="#83c9bd" y={75} />
        <path className="route-personal-accent" d="m108 55 7-6 2 10-7 3Z" fill="#afcfa5" strokeWidth="1" /><circle cx="110" cy="61" r="3" fill="#edd7a6" stroke="none" />
        <path d="M53 102q-12-4-15 9 4 9 15 3m54-12q12-4 15 9-4 9-15 3" fill="#f4fcf5" />
        <g className="route-floating" transform="translate(3 0) rotate(15 30 93)"><path d="m28 112-3-52 5-18 5 18-3 52Z" fill="#e2f5f2" /><path d="M30 52v56" stroke="#99cfc7" strokeWidth="1" /><path d="M20 112q10 5 20 0m-10 3v16" stroke="#bb9a61" strokeWidth="3" /><path d="M30 131q-11 11-17 5" stroke="#88bdb2" /><circle cx="14" cy="137" r="3" fill="#cde6c8" /></g>
      </g> : null}
      {path === "dnf" ? <g stroke="#4d4d67" strokeWidth="1.8">
        <path d="M58 97q-16 11-15 37l21-11 20 10 25-3 8-21-18-16Z" fill="#963f58" /><path d="m50 122 7-14m49 13-6-14" stroke="#c97685" />
        <path d="M58 111h44l2 21-15 3-9-15-9 15-15-3Z" fill="#3e4259" /><path d="M55 132q10-5 18 0v6H53Zm32 0q10-5 18 0l2 6H87Z" fill="#64677a" />
        <path d="M56 98q24-12 48 0l-7 25H63Z" fill="#49536b" /><path d="m68 96 12 16 12-16-4 23H72Z" fill="#dbe3ea" /><path d="M60 119h40" stroke="#af8e61" strokeWidth="4" /><path className="route-personal-accent" d="M77 116h7v7h-7Z" fill="#d4b682" strokeWidth="1" />
        <path d="M48 65q-2-27 32-27t32 27v18q-4 20-32 20T48 83Z" fill="#f4d8c7" />
        <path d="M47 80q-15-30 9-42l-3-9 17 4q14-14 25-4 24-2 23 26l5 10-12-2-2 19-6-23-13 5 4-14-21 18 0-13-16 15-4-3-1 15Z" fill="#e9e9f3" />
        <path d="M57 47q14-10 28-7m9-1 13 8m-35 1-9 9" stroke="#fffefa" strokeWidth="3" /><path d="m101 64 9 6" stroke="#bbc4d7" />
        <Face ink="#48445d" iris="#b87679" y={77} human />
        <path d="M57 99q-15-7-20 5l-2 11 13 6 11-15" fill="#c56574" /><path d="m40 102 5 12m-8-6 13 2" stroke="#ea9b9e" strokeWidth="2" />
        <path d="m103 99 11 1 7 14-12 5-8-13" fill="#798599" /><path d="m110 102 6 9" stroke="#c7d4df" />
        <g transform="rotate(12 126 94)"><path d="M120 116V59l7-22 8 22v57Z" fill="#c1ccd9" /><path d="M127 44v68h8V59Z" fill="#7c879e" stroke="none" /><path d="M127 56v49" stroke="#edf4f7" strokeWidth="1.5" /><path d="M114 114q12 6 26 0l-3 7h-20Z" fill="#bba079" /><path d="M125 121v13" stroke="#8b5368" strokeWidth="6" /><circle cx="125" cy="135" r="3" fill="#bba079" /></g>
      </g> : null}
      {path === "nba" ? <>
        <path d="M105 109q26 12 28-10 0-13-12-9" stroke="#b67848" strokeWidth="10" /><path d="M128 107q7-13-4-17" stroke="#efbc7b" strokeWidth="6" />
        <path d="M58 102h44l3 27H85l-5-12-5 12H55Z" fill="#7261a7" /><path d="M60 126v6m40-6v6" stroke="#f4d0a1" strokeWidth="10" />
        <path d="M53 132q9-9 20-1l1 7H51Zm34-1q11-8 20 1l2 6H86Z" fill="#fff6e6" /><path d="M53 138h20m15 0h19" stroke="#b59269" />
        <path d="m56 90 14-6q10 10 20 0l14 6 0 28H56Z" fill="#8165b7" /><path d="m59 92 0 22m42-22 0 22" stroke="#f6d585" strokeWidth="3" /><path d="M70 89q10 10 20 0" stroke="#f6d585" strokeWidth="3" />
        <text x="80" y="112" textAnchor="middle" fill="#fff2bc" stroke="none" fontSize="14" fontWeight="800" fontFamily="sans-serif">01</text>
        <path d="M47 55 42 27q15 0 24 18m28 0q9-18 24-18l-5 28" fill={body} /><path d="m48 38 6 13m52 0 6-13" stroke="#d99880" strokeWidth="5" />
        <path d="M45 67q-1-25 35-25t35 25v13q-4 21-35 21T45 80Z" fill={body} />
        <path className="route-personal-accent" d="M47 58q33-11 66 0v9q-33-11-66 0Z" fill="#fcf2da" /><path d="m74 49 2 4m8-5 0 4" stroke="#c68a54" strokeWidth="3" /><path d="m48 76 6 2m-5 5 5 1m52-6 6-2m-6 8 5-1" stroke="#c98957" strokeWidth="2" />
        <Face ink={ink} iris="#be814e" y={77} />
        <path d="M54 99q-11-5-15 5t9 13m60-18q11-3 13 10" stroke="#d8a266" strokeWidth="12" /><path d="m42 103-3 7" stroke="#f7f0df" strokeWidth="7" />
        <g className="route-ball"><circle cx="122" cy="115" r="17" fill="#f0a15e" /><path d="M106 115h32m-16-17v34m-12-29q23 12 0 24m24-24q-23 12 0 24" stroke="#986039" strokeWidth="1.5" /><path d="M114 103q6-3 10-2" stroke="#ffd1a0" strokeWidth="2.6" /></g>
      </> : null}
      {path === "honor" ? <>
        <path d="M109 106q25-4 22-26 18 19-2 37l-24 5" fill={body} />
        <path d="M54 95q26-14 52 0l10 28q-36 27-72 0Z" fill={body} />
        <ellipse cx="80" cy="116" rx="23" ry="18" fill="#fff8ed" stroke="none" />
        <ellipse cx="57" cy="134" rx="12" ry="6" fill="#d8bbd8" /><ellipse cx="103" cy="134" rx="12" ry="6" fill="#d8bbd8" />
        <path d="M49 58Q20 20 39 12q19-2 26 35m29 0q7-37 26-35 19 8-10 46" fill={body} />
        <path d="M44 26q-4 9 10 25m52 0q14-16 10-25" stroke="#b28cbf" strokeWidth="8" />
        <path d="M42 64q4-24 38-24t38 24l7 20-10-2 3 12q-38 24-76 0l3-12-10 2Z" fill={body} />
        <path d="M55 83q25-10 50 0l-4 12q-21 15-42 0Z" fill="#fff8ed" stroke="none" />
        <path d="m71 45 9 10 9-10m-9 10 0 7" stroke="#ac83bb" strokeWidth="3" />
        <Face ink={ink} iris="#b082c3" y={76} />
        <path d="M49 103q-17-5-14 9 5 9 18 4m58-13q17-5 14 9-5 9-18 4" fill={body} />
        <path d="M55 101q25 13 50 0" stroke="#9c82b6" strokeWidth="4" />
        <path className="route-personal-accent" d="m74 109 6-5 6 5-6 8Z" fill="#deb66f" strokeWidth="1" />
      </> : null}
      {path === "valorant" ? <>
        <g className="route-floating" fill="#bcece8"><path d="m24 64 9-26 3 22-7 15Z" /><path d="m128 35 10 26-4 13-7-15Z" /></g>
        <path d="M103 104q26 7 22-21 13 23-5 37l-19-7" fill={body} />
        <path d="m56 110 3 22h15l6-19 6 19h15l3-22" fill="#3b5368" /><path d="M58 130h17v8H55Zm27 0h17l3 8H85Z" fill="#e0edef" /><path d="m57 137 17 0m12 0 17 0" stroke="#79d8ce" strokeWidth="2" />
        <path d="m57 91 15-6 8 9 8-9 15 6 5 31H52Z" fill="#487584" /><path className="route-personal-accent" d="m72 93 8 6 8-6 3 29H69Z" fill="#e0eff1" /><path d="m80 100 0 21" stroke="#85c6ca" strokeWidth="2" /><path d="M53 112h16m22 0h16" stroke="#254c61" strokeWidth="5" />
        <path d="M47 53 44 26q18 3 22 18m28 0q4-15 22-18l-3 27" fill={body} /><path d="m49 36 8 16m46 0 8-16" stroke="#83b7c1" strokeWidth="4" />
        <path d="M45 66q0-24 35-24t35 24v17q-5 19-35 19T45 83Z" fill={body} />
        <path d="M45 68q-6-28 28-32 20-3 34-14-1 15-12 23 16-1 19-8 8 17-4 28l-17-7 4-11q-14 22-43 11Z" fill="#f4fdff" /><path d="M56 51q17-1 28-10" stroke="#a3d4db" strokeWidth="2" />
        <Face ink={ink} iris="#62c5c0" y={77} fierce />
        <path d="M49 69h-5v16h6m-6-5-5 5 9 5" stroke="#344a60" strokeWidth="3" /><circle cx="49" cy="88" r="2" fill="#72ded2" stroke="none" />
        <path d="m52 98-12 9 5 12 10-8m51-13 11 9-5 12-9-8" fill="#6db5bd" /><path d="m43 113 7 4m60 0 6-4" stroke="#e4f4f5" strokeWidth="4" />
        <path d="m60 118 7-2m26 0 7 2" stroke="#76dfd0" strokeWidth="2" />
      </> : null}
      {path === "lol" ? <>
        <path d="M57 96q23-11 46 0l8 33q-31 11-62 0Z" fill="#ad4e68" />
        <path d="m67 99 13 12 13-12-6 26H73Z" fill="#fff1e2" /><path d="M57 120h46" stroke={metal} strokeWidth="4" />
        <ellipse cx="62" cy="133" rx="10" ry="5" fill="#f6dfda" /><ellipse cx="98" cy="133" rx="10" ry="5" fill="#f6dfda" />
        <path d="M49 56 47 29q16 1 21 21m24 0q5-20 21-21l-2 27" fill="#55516f" /><path d="m49 34 10 16m42 0 10-16" stroke="#e8b9ca" strokeWidth="5" />
        <path d="M45 65q0-24 35-24t35 24v18q-4 21-35 21T45 83Z" fill={body} />
        <path d="M45 71q-7-32 35-34 38 0 35 34l-9-5-2 17-7-20q-17-2-24-13-1 14-19 16l-4 17Z" fill="#55516f" /><path d="M55 51q10-7 21-6" stroke="#84739a" />
        <Face ink={ink} iris="#bf8b80" y={77} human />
        <path d="m49 82 9 2m-8 4 9 1m43-5 9-2m-10 7 9-1" stroke="#ad748c" strokeWidth="1.5" />
        <path d="m50 102-11 8 5 11 12-9m54-10 11 8-5 11-12-9" fill="#fff1e2" /><path d="m43 118 10-8m54 0 10 8" stroke="#ad4e68" strokeWidth="4" />
        <path className="route-personal-accent" d="m76 113 4-5 4 5-4 5Z" fill={metal} strokeWidth="1" />
      </> : null}
      {path === "nexus" ? <>
        <g className="route-celestial-ring" stroke="#b7a7e6" strokeWidth="1.3"><ellipse cx="80" cy="78" rx="64" ry="38" transform="rotate(-28 80 78)" /><circle cx="25" cy="95" r="4" fill="#d6c4ef" /><circle cx="133" cy="58" r="3" fill="#a5d5e5" /></g>
        <path d="M105 103q33-5 24-34 23 17 11 38-9 15-35 10" fill={body} /><path d="M124 110q17-11 9-29" stroke="#b8a7e2" strokeWidth="1" />
        <path d="M53 83Q25 62 25 83q0 14 23 22-23-3-18 12 9 15 29 1m48-35q28-21 28 0 0 14-23 22 23-3 18 12-9 15-29 1" fill="#8276b1" stroke="#c2b0e8" strokeWidth="1.5" />
        <path d="M60 96q20-10 40 0l8 33-28 9-28-9Z" fill={body} /><path d="M64 103q16 10 32 0l-4 22H68Z" fill="#7776b3" stroke="none" /><ellipse cx="63" cy="133" rx="9" ry="5" fill="#8983be" /><ellipse cx="97" cy="133" rx="9" ry="5" fill="#8983be" />
        <path d="M48 52 39 23q25 2 30 22m22 0q5-20 30-22l-9 29" fill={body} /><path d="m47 32 12 20m42 0 12-20" stroke="#c7b5ec" strokeWidth="5" />
        <path d="M46 62q3-24 34-23t34 23l4 22-9 2 3 7q-12 12-32 11-20 1-32-11l3-7-9-2Z" fill={body} />
        <path d="M88 46a10 10 0 1 0 0 17 9 9 0 0 1 0-17" fill="#f4dfb4" stroke="none" />
        <Face ink="#252746" iris="#beabff" y={78} />
        <path d="M54 99q26 17 52 0l-7 16-19 11-19-11Z" fill="#373858" stroke="#d1b8e6" strokeWidth="1.5" /><path className="route-personal-accent" d="m75 110 5-7 5 7-5 8Z" fill="#dbc9ff" stroke="none" />
        <Spark x={57} y={59} size={3} color="#eee2ff" /><Spark x={103} y={67} size={2} color="#ceeef4" /><Spark x={80} y={126} size={3} color="#e7d4f6" /><circle cx="63" cy="65" r="1.3" fill="#dbc3ff" stroke="none" /><circle cx="102" cy="57" r="1.5" fill="#e5c997" stroke="none" />
        <path d="M52 104q-10-4-11 6 4 8 11 4m56-10q10-4 11 6-4 8-11 4" fill="#9990c9" />
      </> : null}
    </g>
    <RouteRegalia path={path} stage={stage} front />
    <RouteProgress path={path} stage={stage} front />
  </svg>;
}
