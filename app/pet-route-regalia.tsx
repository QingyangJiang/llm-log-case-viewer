import type { IllustratedRoute } from "./pet-route-art";
import { routeMilestoneIndex } from "./pet-route-progress";

/** 进阶直接更换轮廓与服饰；脸部和脚的位置不变，衣柜仍可正常叠穿。 */
export function RouteRegalia({ path, stage, front = false }: { path: IllustratedRoute; stage: number; front?: boolean }) {
  const tier = routeMilestoneIndex(stage);
  if (!tier) return null;
  const mature = tier >= 3, exalted = tier >= 4, final = tier === 5;
  const spread = [0, 0, 4, 10, 17, 23][tier];
  if (!front) return <g data-regalia-tier={tier} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    {path === "eva" && tier >= 2 ? <g stroke="#544270">
      {[-1, 1].map((side) => <g key={side} transform={`translate(80 84) scale(${side} 1)`}>
        <path d={`M28 9 40 ${-36-spread} 53 ${-48-spread} 60 -17 47 24Z`} fill={mature ? "#a680da" : "#7563b1"} />
        <path d={`m44 ${-28-spread} 8-13 2 29-11 22Z`} fill={exalted ? "#d9ff8f" : "#b0e97a"} stroke="none" />
        {exalted ? <path d={`M42 21 62 -34 72 -44 67 7 52 38Z`} fill={final ? "#dfefb9" : "#9c86c3"} stroke="#8baa78" /> : null}
        {final ? <path d="M32 26 73 29 54 45 31 40Z" fill="#a9ca73" /> : null}
      </g>)}
    </g> : null}
    {path === "blade_soul" ? <g stroke="#8cb6b0" fill={mature ? "#b9e1db" : "#dbefde"}>
      <path d={`M57 98Q${31-spread} 101 ${38-spread} ${126+spread/2}Q45 137 67 118m36-20q${26+spread} 3 ${19+spread} ${28+spread/2}Q115 137 93 118`} />
      {mature ? <path d={`M55 110Q${10+spread/2} 72 17 116q11 30 47 18m41-24q${45-spread/2}-38 38 6-11 30-47 18`} fill="#edf5df" /> : null}
      {exalted ? <path d="M42 123Q6 130 16 80q-1 37 39 33m63 10q36 7 26-43 1 37-39 33" fill="#a9d7d1" /> : null}
      {final ? <path d="M33 112Q7 73 26 47q-9 31 24 50m77 15q26-39 7-65 9 31-24 50" fill="#e2efc8" stroke="#b5be7e" /> : null}
    </g> : null}
    {path === "dnf" ? <g stroke="#725067">
      <path d={`M56 91Q${34-spread} 105 ${39-spread} 140l26-8 15 13 16-13 25 8q${5+spread}-35-17-49Z`} fill={exalted ? "#823f58" : "#ab5d6d"} />
      <path d={`M49 110  ${42-spread} 134l18-7m51-17 ${7+spread} 24-18-7`} stroke="#e0a6a2" fill="none" />
      {mature ? <path d="M32 119Q8 97 24 58l3 32 13 7m88 22q24-22 8-61l-3 32-13 7" fill="#bc697b" stroke="#d99599" /> : null}
      {final ? <path d="M27 121Q0 90 18 37q-2 47 20 62m95 22q27-31 9-84 2 47-20 62" fill="#e7a39b" stroke="#c86f80" /> : null}
    </g> : null}
    {path === "nba" && mature ? <g stroke="#ae8854" strokeLinejoin="round">
      <path d={exalted ? "M21 16h118v54l-25-7-34 16-34-16-25 7Z" : "M30 26h100v42l-25-8-25 12-25-12-25 8Z"} fill={final ? "#f5d78d" : exalted ? "#e2c5a0" : "#dad1ed"} strokeWidth="2" />
      <path d={exalted ? "M26 22h108v38l-20-5-34 15-34-15-20 5Z" : "M34 31h92v29l-21-7-25 12-25-12-21 7Z"} fill={final ? "#fff1bc" : "#69558d"} stroke="none" />
      <path d="M80 17v13m-56 5 12 4m100-4-12 4" stroke="#fffbdb" strokeWidth="2" />
      <text x="80" y={exalted ? 41 : 43} fontFamily="sans-serif" fontSize={exalted ? 9 : 10} letterSpacing="1" fontWeight="900" textAnchor="middle" fill={final ? "#725438" : "#fff4d3"} stroke="none">{final ? "LEGEND" : exalted ? "CHAMPIONS" : "ALL STAR"}</text>
      <path d="m42 46 5 1 3 5 3-5 5-1m44 0 5 1 3 5 3-5 5-1" stroke="#f5d18a" strokeWidth="1.5" fill="none" />
      {final ? <><path d="m19 26-5 87 15 17m112-104 5 87-15 17" stroke="#c09a62" strokeWidth="4" fill="none" /><path d="M12 122q15 20 33 21m103-21q-15 20-33 21" stroke="#f5d78d" strokeWidth="3" fill="none" /></> : null}
    </g> : null}
    {path === "honor" && tier >= 2 ? <g stroke="#cba4d0" fill={exalted ? "#e5d6f4" : "#f3e3f1"}>
      <path d={`M48 137q-${12+spread/3} 9-${16+spread/3}-6-17 0-13-15-10-15 4-21 4-13 16-6l10 21m71 27q${12+spread/3} 9 ${16+spread/3}-6 17 0 13-15 10-15-4-21-4-13-16-6l-10 21`} />
      {mature ? <g fill="#d4c0e7"><circle cx="22" cy="77" r={exalted ? 16 : 10} /><circle cx="138" cy="77" r={exalted ? 16 : 10} /></g> : null}
      {final ? <path d="M18 110Q-1 62 32 37q-10 25 0 37m110 36q19-48-14-73 10 25 0 37" fill="#f8e4e9" /> : null}
    </g> : null}
    {path === "valorant" && tier >= 2 ? <g stroke="#9ecbd4" fill="#d6f2ed">
      <path d={`M46 111Q${6+spread/2} ${112-spread} 24 61q-4 33 32 35m48 15q${40-spread/2} ${1-spread} 22-50 4 33-32 35`} />
      {mature ? <path d="M20 116Q-4 76 31 32q-17 43 3 61m106 23q24-40-11-84 17 43-3 61" fill="#b3dfe3" /> : null}
      {exalted ? <path d="M15 130Q50 156 140 114q-35 38-94 34Z" fill="#dff7ee" /> : null}
      {final ? <path d="M12 86Q6 42 57 15L30 43m118 43q6-44-45-71l27 28" stroke="#78bac8" strokeWidth="5" fill="none" /> : null}
    </g> : null}
    {path === "lol" && mature ? <g fill="#d3a1bd" stroke="#b1769e"><path d="M56 106q-23 5-32 29 26 8 43-10m37-19q23 5 32 29-26 8-43-10" />{final ? <path d="M36 133q-29-6-24-35 0 20 29 21m83 14q29-6 24-35 0 20-29 21" fill="#ecc9d8" /> : null}</g> : null}
    {path === "nexus" ? <g stroke="#b4a1d5">{[-1, 1].map((side) => <g key={side} transform={`translate(80 104) scale(${side} 1)`}>{Array.from({length:tier+1},(_,i) => <path key={i} d={`M22 19Q${42+i*3} ${-25-i*8} ${48+i*5} ${-36-i*5}Q${74-i*2} ${2+i*6} 25 30Z`} fill={i%2 ? "#d0bce8" : "#8f83b6"} />)}</g>)}</g> : null}
  </g>;

  return <g data-regalia-front={tier} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    {path === "eva" && tier >= 2 ? <g stroke="#53416c"><path d={mature ? "M51 95 65 98 65 115 54 126 44 113Zm58 0-14 3v17l11 11 10-13Z" : "m51 99 12 5-7 13-11-5Zm58 0-12 5 7 13 11-5Z"} fill={exalted ? "#c0a7e0" : "#8266b0"} /><path d="m51 106 6 3m46 0 6-3" stroke="#d3f699" strokeWidth="3" />{final ? <path d="m60 123 20 10 20-10-4 13H64Z" fill="#c5e79a" /> : null}</g> : null}
    {path === "blade_soul" ? <g stroke="#79a9a3"><path d={tier >= 2 ? "M58 99 44 107l-8 22q13 7 27-9l7-17m32-4 14 8 8 22q-13 7-27-9l-7-17" : "M57 102 44 110l-4 11 18-2m45-17 13 8 4 11-18-2"} fill={exalted ? "#e6f1d3" : "#c8e8df"} />{mature ? <path d="M68 108 56 137l24-6 24 6-12-29-12 9Z" fill="#ebf6ed" /> : null}<path d="M66 113q14 7 28 0" stroke="#c5b079" strokeWidth="3" />{final ? <path d="m69 121 11 9 11-9m-24 12 13-3 13 3" stroke="#aac185" fill="none" /> : null}</g> : null}
    {path === "dnf" ? <g stroke="#4d506a"><path d={mature ? "m51 98-14-2-8 15 18 8 14-11m42-10 14-2 8 15-18 8-14-11" : "m52 99-12 3-2 12 16-4m54-11 12 3 2 12-16-4"} fill={exalted ? "#b6c4d6" : "#7c8a9f"} /><path d="m62 102 18 13 18-13-6 24H68Z" fill={mature ? "#788ba3" : "#4c5b73"} /><path d="m73 113 7 5 7-5-7 11Z" fill="#d7b980" />{tier >= 2 ? <g transform="rotate(12 126 94)"><path d={exalted ? "m117 113-2-61 12-31 15 31-3 61Z" : "m119 114-1-58 9-24 11 24-2 58Z"} fill={final ? "#eddad6" : "#c8d4e1"} /><path d="m127 38 0 69m-4-27 8-9" stroke={final ? "#c37186" : "#7e94b3"} strokeWidth="3" /></g> : null}</g> : null}
    {path === "nba" ? <g stroke="#69577d"><path d="m56 94-14 7-5 19 12 3 14-23m41-6 14 7 5 19-12 3-14-23" fill={exalted ? "#ead19c" : tier >= 2 ? "#fff0d8" : "#735e9d"} /><path d="m42 102 11 3m53 0 11-3" stroke="#f5d28b" strokeWidth="3" /><path d="M61 98q19 12 38 0v25H61Z" fill={final ? "#fff0c0" : exalted ? "#f0d69a" : tier >= 2 ? "#f8eddb" : "#735d9d"} /><path d="M65 103v17m30-17v17m-30-18q15 9 30 0" stroke="#d7ae72" strokeWidth="2" fill="none" /><path d="M73 107h14l-7 7Z" fill={exalted ? "#b58d50" : "#e6ba72"} stroke="none" /><text x="80" y="121" fontSize="12" fontFamily="sans-serif" fontWeight="900" fill="#665180" textAnchor="middle" stroke="none">01</text>{tier >= 2 ? <path d="M41 104v13m78-13v13" stroke={exalted ? "#eee1c4" : "#705e9a"} strokeWidth="5" /> : null}{final ? <><path d="M60 124h40v7H85l-5-8-5 8H60Z" fill="#dcb770" /><path d="m68 127 12 3 12-3" stroke="#fff4cd" strokeWidth="2" fill="none" /></> : null}</g> : null}
    {path === "honor" ? <g stroke="#bb95b9"><path d="M54 99q26 13 52 0l-8 14-18-6-18 6Z" fill={exalted ? "#f5dba2" : "#e8b6cc"} /><path d={mature ? "M68 106q-21 7-28 28l21-2 18-23m13-3q21 7 28 28l-21-2-18-23" : "M73 106 61 124l16-7m10-11 12 18-16-7"} fill={tier >= 2 ? "#f7e3d3" : "#efcada"} /><circle cx="80" cy="109" r={final ? 7 : 5} fill="#ead193" stroke="#b99a70" /></g> : null}
    {path === "valorant" ? <g stroke="#507989"><path d={mature ? "m55 97 12 6-5 30-15-7 7-19m51-10-12 6 5 30 15-7-7-19" : "m55 98 12 5-5 20-13-5Zm50 0-12 5 5 20 13-5Z"} fill={exalted ? "#d1edf1" : "#81b7c3"} /><path d="m71 104 9 6 9-6v18H71Z" fill="#f2f7f3" /><path d="M80 111v11" stroke="#67b4bf" />{final ? <path d="m48 109 10 4m44 0 10-4M63 125h10m14 0h10" stroke="#80dbd3" strokeWidth="4" /> : null}</g> : null}
    {path === "lol" ? <g stroke="#a27690"><path d={tier >= 2 ? "m59 101-17 3-7 20 21 4 12-24m33-3 17 3 7 20-21 4-12-24" : "m59 103-15 6 4 13 15-10m38-9 15 6-4 13-15-10"} fill={mature ? "#e8c7d6" : "#fff1e8"} /><path d="M67 102 80 116l13-14-7 24H74Z" fill={exalted ? "#ead8b6" : "#ebd3c8"} />{mature ? <path d="m74 116-12 20 18-6 18 6-12-20Z" fill={final ? "#d2adc9" : "#b86f8a"} /> : null}<path d="M65 119h30" stroke="#d3b076" strokeWidth="3" /></g> : null}
    {path === "nexus" ? <g stroke="#b6a2d1"><path d={mature ? "M54 99 40 117l11 24 29-13 29 13 11-24-14-18-26 15Z" : "M55 101 49 127l31 10 31-10-6-26-25 12Z"} fill={exalted ? "#6e649c" : "#45456f"} /><path d="m66 116 14 11 14-11-14 20Z" fill={final ? "#f0d2b3" : "#d6c0ed"} /></g> : null}
  </g>;
}
