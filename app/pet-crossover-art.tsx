"use client";

import { useId } from "react";
import { CROSSOVER_ROUTES, type CrossoverRoute } from "./pet-crossover-data";

function Blossom({ x, y, size = 5 }: { x: number; y: number; size?: number }) {
  return <g transform={`translate(${x} ${y}) scale(${size / 5})`} fill="#f8c4db" stroke="#d799bb" strokeWidth=".55">
    {[0, 72, 144, 216, 288].map((angle) => <path key={angle} transform={`rotate(${angle})`} d="M0 0C-6-4-3-10 0-6c3-4 6 2 0 6Z" />)}<circle r="1.4" fill="#ffe8ae" stroke="none" />
  </g>;
}

function FoxShrine({ x, y }: { x: number; y: number }) {
  return <g transform={`translate(${x} ${y})`} stroke="#a580bd" strokeWidth="1.2" strokeLinejoin="round">
    <path d="M-9-9q9-5 18 0L6 9H-6Z" fill="#e7b8df" /><path d="m-7-9-2-10 7 5h4l7-5-2 10-7 5Z" fill="#fff0fa" /><path d="m-4-11 2 2m4 0 2-2M0 9v16m-8 0h16" fill="none" /><circle cy="1" r="3" fill="#e6d3ff" stroke="#b398dc" />
  </g>;
}

function SalonFriend({ kind, x, y }: { kind: "octopus" | "crab" | "seahorse"; x: number; y: number }) {
  return <g className="route-floating" transform={`translate(${x} ${y})`} stroke="#769dd4" strokeWidth="1.1" strokeLinecap="round">
    {kind === "octopus" ? <><path d="M-8 0q-5-15 8-15T8 0l4 6-7-2-5 4-5-4-7 2Z" fill="#c4e9ff" /><path d="M-9-12H9l-3-3v-6H-5v6Z" fill="#5476b2" /></> : kind === "crab" ? <><path d="M-9-2q9-11 18 0v8H-9Z" fill="#b7def9" /><path d="m-8 2-7-8m23 8 7-8m-22 11-7 4m21-4 7 4" /><path d="m-14-6-2-6 7 4m23 2 2-6-7 4" fill="#d9efff" /></> : <><path d="M4-14q-12-8-14 2l3 6 4-2q10 4 5 12-6 6-7 0m6-10 12-6-4 13-7-4" fill="#c6eaff" /><path d="m-4-18 7-5 3 10" fill="#577fb9" /></>}
    <circle cx="-3" cy="-5" r="1" fill="#435c8e" stroke="none" /><circle cx="3" cy="-5" r="1" fill="#435c8e" stroke="none" />
  </g>;
}

/** Transparent painted artwork with cumulative route-specific props and silhouettes. */
export function CrossoverRouteArt({ path, stage }: { path: CrossoverRoute; stage: number }) {
  const uid = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const { palette, milestones, name } = CROSSOVER_ROUTES[path];
  const tier = Math.max(0, [1, 3, 6, 9, 12, 15].filter((threshold) => stage >= threshold).length - 1);
  const id = `crossover-${uid}`;
  const a = tier >= 1, b = tier >= 2, c = tier >= 3, d = tier >= 4, e = tier >= 5;
  return <svg className={`pet-route-illustration route-art-${path}`} data-crossover-tier={tier} viewBox="0 0 160 160" fill="none" aria-hidden="true" focusable="false">
    <defs>
      <linearGradient id={`${id}-gold`} x1="0" y1="0" x2="1" y2="1"><stop stopColor="#fff2c8" /><stop offset=".4" stopColor="#d9ad5f" /><stop offset="1" stopColor="#98703e" /></linearGradient>
      <linearGradient id={`${id}-ice`}><stop stopColor="#e9fcff" /><stop offset="1" stopColor="#89cde8" /></linearGradient>
    </defs>
    <g className="crossover-evolution-back" strokeLinecap="round" strokeLinejoin="round">
      {path === "wukong" ? <>
        {b ? <path d="M26 114q-15-41 9-66m90 66q15-41-9-66" stroke={`url(#${id}-gold)`} strokeWidth="4" /> : null}
        {c ? <g stroke="#b68b45" strokeWidth="1.1"><path d="M70 48Q42 6 13 17q16-2 24 8-12-2-20 5 21-3 53 18Zm20 0Q118 6 147 17q-16-2-24 8 12-2 20 5-21-3-53 18Z" fill={`url(#${id}-gold)`} /></g> : null}
        {d ? <path d="M16 133q-13-14 4-21 12-4 15 8 11-17 25-6 10 8-5 14h48q-14-14 0-19 12-4 17 11 19-10 23 5 2 10-16 12H28q-10 0-12-4Z" fill="#f0d6a2" stroke="#cba96a" strokeWidth="1.2" /> : null}
        {e ? <circle cx="80" cy="78" r="70" stroke={`url(#${id}-gold)`} strokeWidth="4" strokeDasharray="84 5 2 5" /> : null}
      </> : null}
      {path === "nezha" ? <>
        {a ? <path d="M45 86Q-2 32 19 22q22-5 23 22-26-17-9 17m82 25q47-54 26-64-22-5-23 22 26-17 9 17M42 113q-35 40-30 15m106-15q35 40 30 15" stroke="#c95853" strokeWidth="5" /> : null}
        {b ? <circle cx="80" cy="83" r="60" stroke={`url(#${id}-gold)`} strokeWidth="4.5" /> : null}
        {c ? [52, 108].map((x) => <g key={x} transform={`translate(${x} 136)`}><path d="M-10 6q-13-13-4-22 0 10 8 9Q4-23 10-14 6-2 15 0 19 12-3 13Z" fill="#efae5c" /><circle r="9" fill="#cf6650" stroke="#ffd998" strokeWidth="2" /><circle r="3" fill="#ffe5b1" /></g>) : null}
        {d ? <g fill="#c46578" stroke="#efbfaa" strokeWidth="1.2">{[-2,-1,0,1,2].map((i) => <path key={i} transform={`translate(80 141) rotate(${i * 24})`} d="M0 0Q-26-11 0-38 26-11 0 0Z" />)}</g> : null}
        {e ? <g stroke="#d4a561" strokeWidth="6" opacity=".8"><path d="M52 88 25 61 16 39m92 49 27-27 9-22M51 102 21 92 10 75m99 27 30-10 11-17" /><path d="m17 37-5-10m132 10 5-10M9 73 6 64m145 9 3-9" stroke="#ffe0a0" strokeWidth="4" /></g> : null}
      </> : null}
      {path === "aobing" ? <>
        {a ? <g fill={`url(#${id}-ice)`} stroke="#81b7d1" strokeWidth="1">{[[-1,30],[1,130]].map(([side,x]) => <path key={x} d={`M${x} 72l${side * 7} -17 ${side * 9} 16 ${-side * 7} 14Z`} />)}</g> : null}
        {b ? <path d="m20 43-5-14-5 14 5 11Zm120 0 5-14 5 14-5 11Z" fill={`url(#${id}-ice)`} stroke="#89c5e0" /> : null}
        {c ? <path d="M15 130q19-33 36-14-19-3-18 10h89q-4-23 19-21-13 11-1 24-15 17-35 12H41q-27 4-26-11Z" fill="#bce7f4" stroke="#7db9d4" strokeWidth="1.4" /> : null}
        {d ? <g stroke="#82bcd4" strokeWidth="2"><path d="M24 115Q-5 63 33 31 73 1 125 29q32 16 17 41-6 10-17 3l6-11-12 5q-5-20 9-24-24-19-63-9Q14 48 31 98" fill="#c4e9f1" fillOpacity=".72" /><path d="m126 44-6-13 12 9m4 15 12-7-7 14M27 57l10 4m-11 7 9 4m25-38 3 9m7-12 2 9" fill="none" /></g> : null}
        {e ? <><ellipse cx="80" cy="130" rx="72" ry="18" stroke="#88cadf" strokeWidth="3" /><circle cx="134" cy="32" r="10" fill="#d9faff" stroke="#88c5d9" /><path d="m134 19 2 10 7 3-7 2-2 10-3-10-7-2 7-3Z" fill="white" /></> : null}
      </> : null}
      {path === "doraemon" ? <>
        {c ? <g transform="rotate(-8 121 83)" stroke="#c271a7" strokeWidth="1.8"><rect x="94" y="37" width="51" height="102" rx="4" fill="#e7a2ca" /><path d="M102 45h35v85h-35Z" fill="#e8f6ff" /><path d="M109 59h21v24h-21Zm0 34h21v28h-21Z" stroke="#cee1f2" /><circle cx="131" cy="89" r="2.5" fill="#d49c4c" /></g> : null}
        {d ? <g stroke="#7198b4" strokeWidth="1.2"><path d="M21 131q20-15 39-5h64l-10 19H27Z" fill="#9ebbd5" /><path d="M35 126v-21h27v20m-21-20V94h15v11" fill="#c9e2ed" /><rect x="38" y="108" width="19" height="12" rx="2" fill="#5f8eaf" /><circle cx="46" cy="114" r="3" fill="#ffdf8c" /><path d="M32 137h81" stroke="#f2f8f5" strokeWidth="3" /></g> : null}
        {e ? <g stroke="#7fbdd7" strokeWidth="2"><ellipse cx="80" cy="74" rx="70" ry="50" transform="rotate(-24 80 74)" />{[[-1,18,38],[1,138,108],[-1,28,113]].map(([sign,x,y]) => <path key={x} d={`m${x} ${y-6} 2 4 4 2-4 2-2 4-2-4-4-2 4-2Z`} fill={sign === 1 ? "#f5d683" : "#c9edff"} />)}</g> : null}
      </> : null}
      {path === "furina" ? <>
        {a ? <g fill="#d1edff" stroke="#8dbedc" strokeWidth="1">{[[26,60],[133,71]].map(([x,y]) => <path key={x} d={`M${x} ${y-12}q-14 15 0 19 14-4 0-19Z`} />)}</g> : null}
        {b ? <SalonFriend kind="octopus" x={23} y={110} /> : null}
        {c ? <><SalonFriend kind="crab" x={135} y={120} /><SalonFriend kind="seahorse" x={128} y={52} /></> : null}
        {d ? <g stroke="#94a9d4" strokeWidth="1.3"><path d="M10 139V23q70-20 140 0v116l-12-32-9 24-2-90q-47-15-94 0l-2 90-9-24Z" fill="#a9c6e9" fillOpacity=".48" /><path d="M10 24q70 29 140 0" fill="none" stroke="#ddc99d" strokeWidth="3" /></g> : null}
        {e ? <g stroke="#abd8ed" strokeWidth="2"><path d="M12 141q68-28 136 0M23 148q57-20 114 0" /><path d="m58 15 4-8 18 6 18-6 4 8-22 8Z" fill="#dceffd" stroke="#c8bfa1" /></g> : null}
      </> : null}
      {path === "yae_miko" ? <>
        {a ? <><Blossom x={25} y={66} /><Blossom x={132} y={47} size={4} /></> : null}
        {b ? <FoxShrine x={23} y={108} /> : null}
        {c ? <><FoxShrine x={135} y={108} /><FoxShrine x={80} y={25} /><path d="m26 99 52-66 55 66" stroke="#cdb6e5" strokeWidth="1.2" strokeDasharray="3 5" /></> : null}
        {d ? <g fill="#e1c9e7" fillOpacity=".7" stroke="#c0a0d2" strokeWidth="1">{[-2,-1,0,1,2].map((i) => <path key={i} transform={`translate(80 131) rotate(${i * 31})`} d="M0 0Q-42-25 0-69-8-26 8-14 8-4 0 0Z" />)}</g> : null}
        {e ? <><circle cx="80" cy="77" r="70" stroke="#d3b3de" strokeWidth="2" strokeDasharray="46 5" />{[[18,28],[142,36],[20,124],[137,137],[57,14]].map(([x,y]) => <Blossom key={x} x={x} y={y} size={6} />)}</> : null}
      </> : null}
    </g>
    <image href={`/pets/crossover/${path}.webp`} x="8" y="8" width="144" height="144" preserveAspectRatio="xMidYMid meet" className="crossover-portrait" />
    <g className="crossover-evolution-front" strokeLinecap="round" strokeLinejoin="round">
      <path className="route-personal-accent" d="m77 116 3-4 3 4-3 5Z" fill={palette.accent} stroke="#e5d8bd" strokeWidth=".7" />
      {path === "wukong" && a ? <g transform="translate(126 116) rotate(13)" stroke="#89603d" strokeWidth="1"><path d="M-4-12q-8 0-5 7l3 4q-13 10 0 17 12 3 15-5 1-7-6-12l3-5q3-6-5-6Z" fill={`url(#${id}-gold)`} /><path d="M-7-2h10M-3-12v-4h6v4" stroke="#a65040" strokeWidth="2" /></g> : null}
      {path === "doraemon" && a ? <g transform="translate(28 116) rotate(-12)"><ellipse rx="12" ry="8" fill="#bc7e43" stroke="#926039" /><path d="M-12 0q12-5 24 0v3q-12-4-24 0Z" fill="#724b35" /><ellipse cy="-2" rx="11" ry="4" fill="#dfae6b" /></g> : null}
      {path === "doraemon" && b ? <g transform="translate(81 26)" stroke="#9e7837" strokeWidth="1.2"><path d="M0 0v10" strokeWidth="3" /><ellipse rx="22" ry="3" fill="#e7bc61" /><circle r="3" fill="#f9d57d" /></g> : null}
      {path === "yae_miko" && a ? <g transform="translate(128 89) rotate(17)" stroke="#ba847d" strokeWidth="1"><path d="M0 0v36" strokeWidth="2.5" /><path d="M-10 0H9L3 6l5 6-7 6-5-6 5-6-7-3Z" fill="#fff7e8" /><path d="m-3 1 5 5-4 5" stroke="#cbb5d5" /></g> : null}
      {e ? <path d="m57 148 23 5 23-5" stroke={palette.accent} strokeWidth="1.8" /> : null}
      {stage >= 2 ? <g data-evolution-rank={stage}><rect x="117" y="139" width="26" height="14" rx="6" fill="#fff9ee" stroke={palette.accent} /><text x="130" y="149.5" textAnchor="middle" fontSize="9" fontWeight="700" fontFamily="sans-serif" fill={palette.dark}>{stage}</text></g> : null}
    </g>
    <title>{`${name} · ${milestones[tier]} · ${stage} 阶`}</title>
  </svg>;
}
