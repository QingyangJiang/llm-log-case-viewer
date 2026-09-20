import type { ReactNode } from "react";

type FashionPiece = { slot: string; theme: string; primary: string; secondary: string };
const CROPS: Record<string, string> = { headwear: "32 9 96 61", outfit: "39 93 82 48", outerwear: "26 91 108 59", handheld: "108 89 43 52", footwear: "43 122 75 24" };

function Star({ x, y, color }: { x: number; y: number; color: string }) {
  return <path d={`m${x} ${y - 5} 2 3 4 2-4 2-2 4-2-4-4-2 4-2Z`} fill={color} strokeWidth=".8" />;
}
function Bow({ color }: { color: string }) {
  return <g fill={color}><path d="M78 106q-13-11-12 0t12 1m4-1q13-11 12 0t-12 1" /><circle cx="80" cy="106" r="3" /></g>;
}

/** Tailored to the shared face/body anchors. Icons and worn clothes use identical paths. */
export function PetFashionArt({ item, illustrated = true, icon = false }: { item: FashionPiece; illustrated?: boolean; icon?: boolean }) {
  const { slot, theme, primary: p, secondary: s } = item;
  const ink = "#655765", cream = "#fff7e9";
  const formal = ["starlight", "royal", "phoenix", "cosmos"].includes(theme);
  let art: ReactNode = null;
  if (slot === "headwear") art = <>
    {theme === "academy" ? <><path d="M46 43Q37 27 68 25q35-9 44 10l-9 12Z" fill={p} /><path d="M49 43q29-5 55 0v7H49Z" fill={p} /><path d="m74 24 4-7" stroke={p} strokeWidth="5" /><path d="m57 36 5-6 5 6-5 5Z" fill={s} /></> : null}
    {theme === "berry" ? <><path d="M47 43q-8-11 7-17 2-13 18-8 15-10 23 3 17-2 18 13 10 12-5 16H50Z" fill={cream} /><path d="M49 45q31-7 60 0v7H49Z" fill={p} /><path d="M76 29q8-8 15 0l-7 12Z" fill={p} /><path d="m78 28 5-5 5 4" stroke="#689775" /><path d="m81 31 0 2m5 1 0 2" stroke={cream} /></> : null}
    {theme === "cloud" ? <><path d="M48 47Q63 8 100 19q17 3 17 24-10-12-23-8l9 14Z" fill={p} /><path d="M47 45q29-6 57 0v9H47Z" fill={s} /><circle cx="118" cy="43" r="7" fill={s} /><path d="M80 24a8 8 0 1 0 0 13q-9-5 0-13" fill="#ffe9ac" stroke="none" /></> : null}
    {theme === "sailor" ? <><path d="M45 34q35-21 70 0l-8 15H53Z" fill={cream} /><path d="M53 44h54v8H53Z" fill={p} /><path d="M56 52q-13 5-15 14l17-5" fill={p} /><path d="M80 30v10m-6-5q0 10 12 0m-9-5h6" stroke={p} /></> : null}
    {theme === "forest" ? <><path d="M46 43q4-23 31-23t34 23" fill={p} /><path d="M37 44q42-13 86 0-4 14-42 10T37 44Z" fill={s} /><path d="m54 36 10-10m-8 6q-10-10-10 2 2 5 10-2m4-3q-3-13 7-8 4 4-7 8" fill={p} /><circle cx="68" cy="35" r="5" fill={cream} /><circle cx="68" cy="35" r="2" fill="#dfba72" /></> : null}
    {theme === "detective" ? <><path d="M48 44q0-23 31-23t32 23l8 7H41Z" fill={p} /><path d="M78 23v22m-23-7h49M57 27l-2 18m45-17 3 17" stroke={s} strokeWidth="1.5" /><path d="M48 43v14l13-8m49-6v14l-13-8" fill={p} /><circle cx="79" cy="22" r="3" fill={s} /></> : null}
    {theme === "neon" ? <><path d="M44 59V44q1-24 36-24t36 24v15" stroke={p} strokeWidth="7" /><rect x="38" y="47" width="13" height="21" rx="6" fill={p} /><rect x="109" y="47" width="13" height="21" rx="6" fill={p} /><path d="M43 53v10m73-10v10" stroke={s} strokeWidth="4" /><path d="m64 23 5-6h22l5 6" stroke={s} /></> : null}
    {theme === "aurora" ? <><path d="M47 46q-3-29 33-29t33 29v12H99V47H61v11H47Z" fill={p} /><path d="M46 44q34-7 68 0v9q-34-6-68 0Z" fill={s} /><circle cx="80" cy="15" r="8" fill={s} /><path d="M80 27v12m-5-9 10 6m-10 0 10-6" stroke={s} /></> : null}
    {formal ? <><path d={theme === "phoenix" ? "M54 46 46 31l19 5L80 16l15 20 19-5-8 15Z" : theme === "cosmos" ? "M51 47 57 26l15 9 8-22 8 22 15-9 6 21Z" : theme === "starlight" ? "M52 47 58 34l13 7 9-18 9 18 13-7 6 13Z" : "M51 47 48 27l21 10 11-20 11 20 21-10-3 20Z"} fill={s} /><path d="M53 47q27-7 54 0v6H53Z" fill={p} /><Star x={80} y={38} color={p} />{theme === "phoenix" ? <path d="M51 40q-15 13-17 1m74-1q15 13 17 1" stroke={s} strokeWidth="3" /> : null}</> : null}
  </>;
  if (slot === "outfit") art = <>
    <path d={theme === "cloud" || theme === "neon" ? "M57 99 68 96q12 9 24 0l11 3 8 15-9 4-3-8 4 25H84l-4-11-4 11H57l4-25-3 8-9-4Z" : theme === "berry" || theme === "forest" || formal ? "M59 98q21 10 42 0l7 10-10 4 15 20q-33 14-66 0l15-20-10-4Z" : "M57 98q23 10 46 0l9 13-12 5-1 18q-19 7-38 0l-1-18-12-5Z"} fill={p} />
    {theme === "academy" ? <><path d="m68 100 12 13 12-13-12 5Z" fill={cream} /><path d="m80 109-4 15 4 4 4-4Z" fill={s} /><path d="M62 123h36m-37 7h39m-30-12v17m20-17v17" stroke={s} strokeWidth=".9" opacity=".6" /></> : null}
    {theme === "berry" ? <><path d="M64 112q16 9 32 0l7 19q-23 10-46 0Z" fill={cream} /><Bow color={s} /><path d="m75 121 5-3 5 3-5 7Z" fill={p} /><path d="M51 132q3 7 7 0 4 8 8 2 5 7 9 1 5 7 10 0 5 6 9-1 4 6 8-2 5 7 8 0" fill={s} /></> : null}
    {theme === "cloud" ? <><path d="M69 110q11-8 22 0v14H69Z" fill={s} /><circle cx="80" cy="109" r="2" fill={p} /><path d="M67 100q13 12 26 0" stroke={s} strokeWidth="4" /><Star x={59} y={113} color="#ffe9ad" /></> : null}
    {theme === "sailor" ? <><path d="m63 100 17 16 17-16-4 12-13 10-13-10Z" fill={cream} /><path d="M61 128h38m-37 5h36" stroke={cream} strokeWidth="3" /><Bow color={s} /></> : null}
    {theme === "forest" ? <><path d="M69 104h22l7 26q-18 7-36 0Z" fill={s} /><path d="M78 115v13m0-6q-9-11-10-3 3 7 10 3m0-2q12-10 11-1-4 6-11 1" stroke={p} fill={p} /><circle cx="80" cy="112" r="4" fill={cream} /></> : null}
    {theme === "detective" ? <><path d="m68 101 12 13 12-13-4 27H72Z" fill={s} /><path d="M80 115v18m-15-11h7m16 0h7" stroke={ink} /><circle cx="84" cy="122" r="1.4" fill={ink} /><circle cx="84" cy="129" r="1.4" fill={ink} /></> : null}
    {theme === "neon" ? <><path d="m66 101 4 30m24-30-4 30M54 113l12 3m28 0 12-3" stroke={s} strokeWidth="2.5" /><path d="M74 111h12v8H74Z" fill={s} /><path d="m80 122 0 8" stroke={cream} /></> : null}
    {theme === "aurora" ? <><path d="M60 101q20 11 40 0m-38 31q18 7 36 0M80 110v24" stroke={s} strokeWidth="6" /><circle cx="75" cy="118" r="2" fill={s} /><circle cx="75" cy="125" r="2" fill={s} /></> : null}
    {formal ? <><path d={theme === "phoenix" ? "M65 101 90 123l-6 10-19-27m29-5-26 22" : "M67 101q13 9 26 0l-7 16 18 15q-24 8-48 0l18-15Z"} fill={s} /><path d="M59 127q21 12 42 0" stroke={cream} strokeWidth="1" /><Star x={80} y={115} color={p} />{theme === "cosmos" ? <path d="M63 127q6-12 17 0t17-1" stroke={p} /> : null}</> : null}
  </>;
  if (slot === "outerwear") art = <>
    <path d={theme === "berry" || theme === "neon" ? "M57 99 44 104l-9 21 17 5 9-22m42-9 13 5 9 21-17 5-9-22" : theme === "detective" || formal ? "M59 97 44 108l-10 31 24 2 8-36m35-8 15 11 10 31-24 2-8-36" : "M60 98 43 105l-13 23q15 10 30-8l7-16m33-6 17 7 13 23q-15 10-30-8l-7-16"} fill={theme === "berry" ? cream : p} />
    <path d="M56 99q24 14 48 0l-8 10-16-3-16 3Z" fill={s} />
    <circle cx="80" cy="106" r="3" fill={p} />
    {theme === "aurora" || theme === "cloud" ? <path d="M42 109 34 124m84-15 8 15" stroke={s} strokeWidth="6" /> : null}
    {theme === "neon" ? <path d="m43 114-3 8 12 4m65-12 3 8-12 4" stroke={s} strokeWidth="3" /> : null}
    {theme === "forest" ? <path d="M43 110q-6 9-4 14m0-5 10-4m68-5q6 9 4 14m0-5-10-4" stroke={s} /> : null}
    {theme === "starlight" || theme === "cosmos" ? <><Star x={44} y={128} color={s} /><Star x={116} y={128} color={s} /></> : null}
    {theme === "phoenix" ? <path d="m44 113-4 20 9-11m67-9 4 20-9-11" stroke={s} strokeWidth="3" /> : null}
    {theme === "royal" ? <path d="m43 113-6 24 18 1m62-25 6 24-18 1" stroke={s} strokeWidth="3" /> : null}
    {theme === "academy" || theme === "sailor" ? <path d="m40 119-3 7 14-1m69-6 3 7-14-1" stroke={s} /> : null}
    {theme === "detective" ? <path d="m54 101-7 9 7 3-13 23m65-35 7 9-7 3 13 23" stroke={s} /> : null}
  </>;
  if (slot === "handheld") art = <g transform="rotate(12 126 118)">
    {theme === "academy" ? <><path d="M113 101h24v30h-24Z" fill={p} /><path d="M117 101v30m4-24h11m-11 5h8" stroke={s} /><path d="M118 128h18" stroke={cream} /></> : null}
    {theme === "berry" ? <><path d="m115 118 3 15h17l3-15" fill={p} /><path d="M113 119q0-8 7-9-1-7 7-7t7 7q8 1 8 9Z" fill={cream} /><path d="m123 106 4-7 4 7-4 4Z" fill={p} /><path d="m123 125 0 6m7-6 0 6" stroke={s} /></> : null}
    {theme === "cloud" ? <><path d="M114 102q13 4 26 0-4 14 0 28-13-4-26 0 4-14 0-28Z" fill={p} /><path d="M130 109a8 8 0 1 0 0 14q-10-6 0-14" fill={s} stroke="none" /></> : null}
    {theme === "sailor" ? <><path d="m111 119 28-17 6 11-28 17Z" fill={s} /><path d="m112 119 6 11m9-20 6 11" stroke={p} strokeWidth="6" /><ellipse cx="142" cy="107" rx="4" ry="7" fill="#bce0e2" /></> : null}
    {theme === "forest" ? <><path d="M115 119q-1-22 12-22t12 22" stroke={s} strokeWidth="3" /><path d="m113 117 4 17h21l4-17Z" fill={s} /><path d="m122 119-3-17m10 17 5-19" stroke={p} /><circle cx="119" cy="105" r="4" fill={cream} /><circle cx="132" cy="109" r="4" fill={cream} /><path d="M117 122h22m-20 5h18" stroke={p} /></> : null}
    {theme === "detective" ? <><circle cx="125" cy="111" r="12" fill="#cbe7df" fillOpacity=".85" stroke={s} strokeWidth="4" /><path d="m126 124 2 13" stroke={p} strokeWidth="6" /><path d="M119 109q0-5 6-5" stroke={cream} strokeWidth="3" /></> : null}
    {theme === "neon" ? <><rect x="114" y="99" width="25" height="35" rx="5" fill={p} /><path d="M119 105h15v20h-15Z" fill="#273e5b" /><path d="m121 113 4 3-4 3m7 1h4" stroke={s} /><circle cx="126" cy="130" r="1.5" fill={s} /></> : null}
    {theme === "aurora" ? <><path d="M121 105q-7-13 5-13t5 13M114 109h24l-3 23h-18Z" fill={s} /><path d="m114 109 12-9 12 9m-11 2v17m-6-10 12 7m-12 0 12-7" stroke={p} /></> : null}
    {theme === "phoenix" ? <><path d="M126 122v15" stroke={p} strokeWidth="4" /><circle cx="126" cy="109" r="16" fill={s} /><path d="M118 117q-7-12 14-16-10 6-2 15-5-5-12 1Z" fill={p} /><path d="m126 126 8 7" stroke={s} /></> : null}
    {theme === "starlight" || theme === "royal" ? <><path d="M126 109v28" stroke={s} strokeWidth="4" />{theme === "royal" ? <path d="m116 101 2-10 8 6 8-6 2 10-10 11Z" fill={s} /> : <circle cx="126" cy="104" r="12" stroke={s} />}<Star x={126} y={103} color={p} /></> : null}
    {theme === "cosmos" ? <><circle cx="126" cy="112" r="12" fill={p} /><ellipse cx="126" cy="112" rx="20" ry="7" transform="rotate(-25 126 112)" stroke={s} /><Star x={123} y={109} color={s} /><path d="M126 125v9m-8 0h16" stroke={p} strokeWidth="3" /></> : null}
  </g>;
  // Round toes are intentionally retained from the original wardrobe.
  if (slot === "footwear") art = <g fill={p}><path d="M51 130q10-8 20 0v9H49Z" /><path d="M89 130q10-8 20 0l2 9H89Z" /><path d="M52 135h17m22 0h17" stroke={s} strokeWidth="3" /></g>;
  const offset = icon || illustrated ? 0 : slot === "headwear" ? -15 : slot === "footwear" ? -7 : -3;
  return <svg className={icon ? "pet-fashion-icon" : `pet-fashion-art pet-fashion-art-${slot}`} viewBox={icon ? CROPS[slot] : "0 0 160 160"} fill="none" aria-hidden="true" focusable="false">
    <g transform={`translate(0 ${offset})`} stroke={ink} strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round">{art}</g>
  </svg>;
}
