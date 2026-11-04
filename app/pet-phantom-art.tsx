"use client";

import { useId } from "react";
import { PHANTOM_ROUTES, type PhantomRoute } from "./pet-phantom-data";

function Blade({ x, y, angle = 0, color = "#ead8b2", scale = 1 }: { x: number; y: number; angle?: number; color?: string; scale?: number }) {
  return <g transform={`translate(${x} ${y}) rotate(${angle}) scale(${scale})`} stroke="#63514b" strokeWidth="1.5" strokeLinejoin="round">
    <path d="m0-38 4 11-1 42h-6l-1-42Z" fill={color} /><path d="M0-29V12" stroke="#fff4dc" strokeWidth="1" />
    <path d="M-9 16q9-4 18 0l-1 3H-8Z" fill="#c5a466" /><path d="M-2 19h4v13h-4Z" fill="#4b3a45" /><path d="M-2 23h4m-4 4h4" stroke="#c5a466" /><circle cy="34" r="3" fill="#c5a466" />
  </g>;
}

function Face({ hair = "#292e37", eyes = "#755456", feminine = false }: { hair?: string; eyes?: string; feminine?: boolean }) {
  return <>
    <path d="M47 64q-2-30 33-30t33 30l1 29-10 9H56L46 91Z" fill={hair} />
    <path d="M49 65q6-22 31-22t31 22v14q-2 23-31 25-29-2-31-25Z" fill="#f6e6d6" stroke="#584342" strokeWidth="1.4" />
    <path d="M46 67q0-34 34-34t34 34l-15-9-1 8-14-14-5 9-12-11q-5 13-21 17Z" fill={hair} />
    <path d="m54 69 11-3m30 0 11 3" stroke={hair} strokeWidth="1.6" />
    <g fill="#322f39" stroke="none"><ellipse cx="64" cy="77" rx="4.5" ry="6" /><ellipse cx="96" cy="77" rx="4.5" ry="6" /><ellipse cx="65" cy="79" rx="2.7" ry="3" fill={eyes} /><ellipse cx="97" cy="79" rx="2.7" ry="3" fill={eyes} /><circle cx="63" cy="75" r="1.5" fill="#fff9ed" /><circle cx="95" cy="75" r="1.5" fill="#fff9ed" /></g>
    {feminine ? <path d="m59 74-3-2m45 2 3-2" stroke="#322f39" strokeWidth="1.5" /> : null}
    <ellipse cx="56" cy="86" rx="4" ry="2" fill="#d69d97" opacity=".45" stroke="none" /><ellipse cx="104" cy="86" rx="4" ry="2" fill="#d69d97" opacity=".45" stroke="none" />
    <path d="M77 91q3 3 7-1" stroke="#9c6867" strokeWidth="1.5" fill="none" />
  </>;
}

function Soul({ tier, body }: { tier: number; body: string }) {
  const mature = tier >= 4;
  return <g stroke="#29333b" strokeWidth="1.7" strokeLinejoin="round" strokeLinecap="round">
    {mature ? <path d="M54 96q-20 4-31 43l21-5 8 11 28-19 28 19 8-11 21 5q-11-39-31-43Z" fill="#37424a" /> : null}
    <path d="M77 104Q25 110 15 79q9 12 31 12-15-9-9-24 5 21 42 28" fill="#b24b4d" />
    {tier >= 1 ? <path d="M94 98q33 7 48-20 5 22-17 34l12 13q-26 5-43-19M57 100q-29 25-44 12 19-1 28-21" fill="#cb6257" /> : null}
    {tier >= 2 ? <Blade x={30} y={92} angle={-22} color="#a9b7b9" scale={tier >= 5 ? 1.12 : .9} /> : null}
    <path d="M57 98q23-11 46 0l7 34-16 6H64l-14-6Z" fill={body} />
    <path d="m61 97 19 14 20-14-8 32H67Z" fill="#25323b" /><path d="m64 104 17 10 17-10M63 122h35" fill="none" stroke="#c4ad83" strokeWidth="2" />
    <path d="m62 126-6 11q4 6 17 2l4-11m8 0 3 12q13 3 17-3l-6-11" fill="#28313a" /><path d="M58 138h15m15 0h15" stroke="#93836e" strokeWidth="2.5" />
    <path d="m55 99-12 7-4 18 13 2 10-19m43-8 12 7 4 18-13 2-10-19" fill="#45545b" /><path d="m41 116 12 3m54 0 12-3" stroke="#b6a98b" strokeWidth="3" />
    <path d="M71 38q-10-14 1-21 15-8 20 6l-2 15" fill="#252e36" /><path d="m70 26 21-1" stroke="#ba5452" strokeWidth="4" />
    <Face eyes="#a4625d" /><path d="m104 80-3 8" stroke="#bd7c75" strokeWidth="1.2" />
    <path d="M52 96q28 10 55-1l-3 12q-23 9-49 0Z" fill="#b65350" />
    <Blade x={126} y={91} angle={17} color={tier >= 4 ? "#db7660" : "#b65d59"} scale={tier >= 3 ? 1.12 : .94} />
    <path className="route-personal-accent" d="m74 122 6-4 6 4-6 5Z" fill="#c9aa73" strokeWidth="1" />
    {tier >= 4 ? <path d="m28 135 14-8 7 10m83-2-14-8-7 10M57 118l-3 13m49-13 3 13" fill="none" stroke="#a69a83" /> : null}
  </g>;
}

function Zuoshang({ tier, body }: { tier: number; body: string }) {
  return <g stroke="#5e5548" strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round">
    <path d={tier >= 4 ? "M54 94 31 137l21-4 12 9 16-25 16 25 12-9 21 4-23-43Z" : "M56 97 43 132l18 6 19-15 19 15 18-6-13-35Z"} fill="#424440" />
    <path d="M58 96q22-9 44 0l11 37-33 9-33-9Z" fill={body} /><path d="m63 98 17 16 17-16-8 33H71Z" fill="#4b4740" />
    <path d="m63 99 17 13 17-13m-39 30 22 7 22-7M59 119h42" stroke="#c5a469" strokeWidth="3" fill="none" />
    <path d="M57 136h18v6H55Zm28 0h18l2 6H85Z" fill="#3c3b3b" />
    <path d="m55 98-13 8-5 20 15 2 11-24m42-6 13 8 5 20-15 2-11-24" fill="#d4c7a7" />
    {tier >= 1 ? <path d="m56 95-17 6-2 12 20-3 6-10m41-5 17 6 2 12-20-3-6-10" fill="#ceb173" /> : null}
    <path d="M70 39q-8-17 1-23l18 1q8 9 0 22" fill="#292f32" /><path d="m69 25 11-8 12 8-4 5H73Z" fill="#d6b575" /><path d="M80 18v18" stroke="#eddbb0" strokeWidth="2" />
    <Face eyes="#9d864d" hair="#303536" />
    <path d="M53 99q27 11 54 0l-5 10-22 7-22-7Z" fill="#eee2c5" /><path d="m65 106 15 7 15-7" stroke="#c8a96b" />
    <Blade x={128} y={94} angle={14} color="#9a83ad" scale={tier >= 3 ? 1.08 : .92} />
    {tier >= 1 ? <><path d="M40 123q-10 16-15 11" stroke="#c4b482" /><circle cx="25" cy="135" r="3" fill="#8fb1a0" /></> : null}
    <path className="route-personal-accent" d="m76 120 4-4 4 4-4 7Z" fill="#c3bc92" />
  </g>;
}

function Guard({ x, y, jade = false, large = false }: { x: number; y: number; jade?: boolean; large?: boolean }) {
  const metal = jade ? "#b5d4bf" : "#5b6464", edge = jade ? "#46766c" : "#b6a17b";
  return <g className="route-floating" transform={`translate(${x} ${y}) scale(${large ? 1.08 : .8})`} stroke={edge} strokeWidth="1.5" strokeLinejoin="round">
    <path d="m-10-5-8 11 6 8 5-12m17-7 8 11-6 8-5-12" fill={metal} /><path d="m-10-6 10-5 10 5 2 20-12 5-12-5Z" fill={metal} />
    <path d={jade ? "M-10-17-5-27 0-20l5-7 5 10v12H-10Z" : "M-12-20-5-23h10l7 3-2 16H-10Z"} fill={metal} />
    <path d="m-7-14 4 2m6 0 4-2" stroke={jade ? "#f5e6bd" : "#d99178"} strokeWidth="2.5" /><path d="M-4-6h8M-6 13l-3 10m15-10 3 10" />
    <path d="m-3 1 3-3 3 3-3 4Z" fill={jade ? "#faf3cd" : "#c87d6e"} />
  </g>;
}

function Xiaokui({ tier, body }: { tier: number; body: string }) {
  return <g stroke="#466158" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round">
    <path d="M55 52q-17 16-13 65l20-9m43-56q17 16 13 65l-20-9" fill="#303e41" />
    <path d={tier >= 4 ? "M59 94q21-8 42 0l17 43-38 8-38-8Z" : "M59 94q21-8 42 0l12 40-33 9-33-9Z"} fill={body} />
    <path d="m65 96 15 15 15-15-6 28H71Z" fill="#eff1d9" /><path d="M56 121q24 12 48 0l-2 10q-22 12-44 0Z" fill="#b8cdb5" />
    <path d="M54 135q26 8 52 0m-44-7-3 8m39-8 3 8" stroke="#e8e0bc" strokeWidth="2" /><path d="M58 140h15m14 0h15" stroke="#586c63" strokeWidth="5" />
    <path d={tier >= 1 ? "m57 97-18 6-13 23q15 13 31-4l8-20m38-5 18 6 13 23q-15 13-31-4l-8-20" : "m57 97-13 7-5 17 14 3 11-23m39-4 13 7 5 17-14 3-11-23"} fill="#8fb7a0" />
    <path d="M40 116q6 10 15 3m50 0q9 7 15-3" stroke="#e7dabc" strokeWidth="3" />
    <circle cx="53" cy="42" r="11" fill="#334044" /><circle cx="107" cy="42" r="11" fill="#334044" />
    <path d="m47 34 9 15m57-15-9 15" stroke="#c57570" strokeWidth="3" />
    <Face feminine eyes="#779b80" hair="#334044" />
    <path d="M49 51 37 42m74 9 12-9" stroke="#c8b780" strokeWidth="2.5" /><path d="m39 42 1-8 7 7m74 1-1-8-7 7" fill="#d9dabc" />
    <path d="M57 99q23 7 46 0l-9 9-14-3-14 3Z" fill="#c9837b" /><path className="route-personal-accent" d="m76 119 4-5 4 5-4 7Z" fill="#9bbbaa" />
    {tier >= 2 ? <Guard x={23} y={116} jade large={tier >= 5} /> : null}
    {tier >= 3 ? <Guard x={136} y={116} large={tier >= 5} /> : null}
    {tier >= 5 ? <path d="M55 37q25-15 50 0m-43-3-2-8 9 5m22 0 9-5-2 8" fill="none" stroke="#c4bb87" strokeWidth="2" /> : null}
  </g>;
}

function Xianzhe({ tier, body }: { tier: number; body: string }) {
  return <g stroke="#59434c" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round">
    <path d="M52 51q-16 16-12 81l21-12m47-69q16 16 12 81l-21-12" fill="#383340" />
    <path d={tier >= 4 ? "M58 98h44l24 40-46 7-46-7Z" : "M58 98h44l14 39-36 8-36-8Z"} fill={body} />
    <path d="m65 100 15 13 15-13-8 27H73Z" fill="#f1e4d3" /><path d="m57 128 23 10 23-10m-45 10 22 4 22-4" fill="none" stroke="#d2b78b" strokeWidth="2" />
    <path d={tier >= 1 ? "m59 98-18 5-11 28q15 4 28-10l10-18m33-5 18 5 11 28q-15 4-28-10l-10-18" : "m59 98-13 8-6 19 15-1 12-21m34-5 13 8 6 19-15-1-12-21"} fill="#7b6473" />
    <path d="m34 127 14-3m64 0 14 3" stroke="#d3b88d" strokeWidth="3" />
    <Face feminine eyes="#a77c84" hair="#373441" />
    <path d="M49 50q31-16 62 0" stroke="#a97478" strokeWidth="3" /><path d="m53 48-14-4 7 12 7-4m54-4 14-4-7 12-7-4" fill="#aa626b" />
    <path d="M42 51v16m76-16v16" stroke="#c8ae7f" /><circle cx="42" cy="68" r="2" fill="#c8ae7f" /><circle cx="118" cy="68" r="2" fill="#c8ae7f" />
    <g transform="rotate(23 81 116)">
      <path d="M78 83h7v26q19 7 19 20-1 14-22 14t-22-14q0-14 18-20Z" fill="#d6b58b" /><path d="M80 88h3v33" stroke="#fcf0d4" strokeWidth="4" />
      <path d="M79 84h6l2-9h-8Z" fill="#6c4b52" /><path d="M76 79h4m5 2h5m-14 5h4m5 2h5" stroke="#b49866" strokeWidth="2" />
      <path d="M72 120q-8 10 2 15m18-15q8 10-2 15" fill="none" stroke="#926c58" /><path d="M78 104v32m3-32v32m3-32v32m3-32v32" stroke="#fff2ce" strokeWidth=".8" /><path d="M75 136h15" stroke="#76525c" strokeWidth="3" />
      {tier >= 1 ? <path d="M64 129q1 11 18 11t18-11m-24-19 6 4 7-4" stroke="#f5ddad" fill="none" strokeWidth="2" /> : null}
      <path className="route-personal-accent" d="m78 118 4-4 4 4-4 5Z" fill="#ba8d91" />
    </g>
    <circle cx="61" cy="116" r="4" fill="#f3e0ce" /><circle cx="101" cy="104" r="4" fill="#f3e0ce" /><path d="m58 116 5 1m35-13 5 1" stroke="#a6877a" />
  </g>;
}

/** Six cumulative silhouettes, shared by studio, wardrobe, homestead and desktop. */
export function PhantomRouteArt({ path, stage }: { path: PhantomRoute; stage: number }) {
  const uid = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const { palette, milestones } = PHANTOM_ROUTES[path];
  const tier = Math.max(0, [1, 3, 6, 9, 12, 15].filter((threshold) => stage >= threshold).length - 1);
  const body = `url(#phantom-${uid}-robe)`;
  return <svg className={`pet-route-illustration route-art-${path}`} data-phantom-tier={tier} viewBox="0 0 160 160" fill="none" aria-hidden="true" focusable="false">
    <defs><linearGradient id={`phantom-${uid}-robe`} x1="51" y1="96" x2="108" y2="142" gradientUnits="userSpaceOnUse"><stop stopColor={palette.light} /><stop offset="1" stopColor={palette.base} /></linearGradient></defs>
    <ellipse cx="80" cy="143" rx={tier >= 4 ? 58 : 37} ry="6" fill={palette.dark} opacity=".12" />
    <g className="route-radiance" stroke={palette.accent} strokeWidth="2" strokeLinecap="round">
      {path === "phantom_soul" && tier >= 3 ? <path d="M14 111Q-4 25 105 17 31 36 24 96" fill="#dba39a" fillOpacity=".18" /> : null}
      {path === "phantom_soul" && tier >= 5 ? <path d="M128 32q48 79-31 109 48-39 31-109Z" fill="#b9504e" fillOpacity=".45" /> : null}
      {path === "phantom_zuoshang" && tier >= 4 ? <path d="M17 123Q-2 57 54 23l15 3-10 9 17-2-8 12-17-1q-27 30-17 54m105 20q22-45-8-70l-13 1 6 9-10-2 9 14" stroke="#d4b367" strokeWidth="5" /> : null}
      {path === "phantom_zuoshang" && tier >= 3 ? <path d="M20 117V75a60 53 0 0 1 120 0v42m-120-3 11-9m109 9-11-9" stroke="#d4b367" strokeWidth="2.5" /> : null}
      {path === "phantom_xiaokui" && tier >= 4 ? <path d="M13 95q-6-68 35-61m-30 90Q9 151 53 143m94-48q6-68-35-61m30 90q9 27-35 19" stroke="#ca827d" strokeWidth="4" /> : null}
      {path === "phantom_xianzhe" && tier >= 2 ? <><path d="M33 62q-26 33 2 67m90-67q26 33-2 67" /><path d="M23 58q-31 42 1 77m112-77q31 42-1 77" opacity={tier >= 3 ? 1 : .2} /></> : null}
      {path === "phantom_xianzhe" && tier >= 3 ? <path d="M19 39Q-5 90 17 141m124-102q24 51 2 102M18 40l8-10 5 10-5 8Zm124 0-8-10-5 10 5 8Z" fill="#dcc092" fillOpacity=".4" /> : null}
      {path === "phantom_xianzhe" && tier >= 4 ? <path d="m18 43 124 83M17 85l118-46M32 23l96 119" stroke="#ba7e87" strokeWidth="1.2" /> : null}
      {path === "phantom_xianzhe" && tier >= 5 ? <circle cx="80" cy="77" r="69" stroke="#ccb385" strokeWidth="4" strokeDasharray="115 12 28 12" /> : null}
    </g>
    {path === "phantom_zuoshang" && tier >= 2 ? <g className="route-floating">{(tier >= 5 ? [-65, -42, -20, 20, 42, 65] : tier >= 3 ? [-49, 0, 49] : [-49, 49]).map((angle) => <Blade key={angle} x={80 + angle * .8} y={angle === 0 ? 43 : 67} angle={angle} color="#e4c98c" scale={.66} />)}</g> : null}
    {path === "phantom_soul" ? <Soul tier={tier} body={body} /> : path === "phantom_zuoshang" ? <Zuoshang tier={tier} body={body} /> : path === "phantom_xiaokui" ? <Xiaokui tier={tier} body={body} /> : <Xianzhe tier={tier} body={body} />}
    {tier >= 5 ? <g stroke={palette.accent} strokeWidth="1.5"><path d="m53 147 27 5 27-5" /><path d="m76 150 4-5 4 5-4 5Z" fill="#ead4a2" /></g> : null}
    {stage >= 2 ? <g data-evolution-rank={stage}><rect x="114" y="135" width="25" height="15" rx="6" fill="#fff5e4" stroke={palette.accent} /><text x="126.5" y="146" textAnchor="middle" fill={palette.dark} fontSize="10" fontWeight="700" fontFamily="sans-serif">{stage}</text></g> : null}
    <title>{`${PHANTOM_ROUTES[path].name} · ${milestones[tier]} · ${stage} 阶`}</title>
  </svg>;
}
