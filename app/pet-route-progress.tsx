import type { IllustratedRoute } from "./pet-route-art";

export const ROUTE_MILESTONES: Record<IllustratedRoute, readonly string[]> = {
  eva: ["紫绿机体", "肩甲展开", "AT 力场", "核心觉醒", "领域扩张", "同步突破"],
  blade_soul: ["灵族剑士", "流云剑穗", "双剑护身", "御剑剑阵", "剑气流转", "剑心通明"],
  dnf: ["鬼剑冒险", "鬼手锁链", "血气觉醒", "巨剑锋芒", "剑痕爆发", "阿拉德勇士"],
  nba: ["新秀登场", "护臂上场", "全明星", "冠军奖杯", "主场聚光", "传奇球星"],
  honor: ["入梦之灵", "梦力泡泡", "梦境护盾", "梦境环游", "幻梦森林", "寻梦之旅"],
  valorant: ["疾风特工", "乘风起势", "浮空飞刃", "五刃齐发", "逐风轨迹", "王牌时刻"],
  lol: ["灵狐来客", "灵魂宝珠", "狐火环绕", "灵魄突袭", "九尾舒展", "灵魂共鸣"],
  nexus: ["未知来客", "月相流转", "星羽展开", "双重星轨", "星图浮现", "次元观测"],
};
export const ROUTE_STAGE_THRESHOLDS = [1, 3, 6, 9, 12, 15] as const;
export function routeMilestoneIndex(stage: number) {
  return Math.max(0, ROUTE_STAGE_THRESHOLDS.filter((value) => stage >= value).length - 1);
}
export function routeMilestone(path: IllustratedRoute, stage: number) {
  return ROUTE_MILESTONES[path][routeMilestoneIndex(stage)];
}

/** Route-specific, cumulative silhouettes; the face area stays clear. */
export function RouteProgress({ path, stage, front = false }: { path: IllustratedRoute; stage: number; front?: boolean }) {
  const a = stage >= 3, b = stage >= 6, c = stage >= 9, d = stage >= 12, e = stage >= 15;
  if (front) return <g data-route-progress="front" fill="none" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2">
    {path === "eva" && a ? <path d="m23 53 9 30m96 0 9-30" stroke="#c7fc75" strokeWidth={b ? 5 : 3} /> : null}
    {path === "eva" && c ? <path d="m70 113 10-8 10 8-10 11Z" fill="#ff986a" stroke="#ffe8ad" /> : null}
    {path === "blade_soul" && a ? <path d="M43 108q-19 18-25 10m19-5q-4 19-17 20" stroke="#6bbfb5" strokeWidth="3" /> : null}
    {path === "dnf" && a ? <g><path d="m47 96-10 9 4 16 13-12Z" fill="#c75360" stroke="#692f52" /><path d="m38 101 10 7m-11-1 10 7m-8-1 7 6" stroke="#e5ced5" strokeWidth="3" /></g> : null}
    {path === "nba" && a ? <path d="m38 99-4 14" stroke="#665296" strokeWidth="8" /> : null}
    {path === "nba" && b ? <path d="m59 94 3-5 3 5-3 4Z" fill="#ffe295" stroke="#fff5d6" strokeWidth="1" /> : null}
    {path === "nba" && c ? <g fill="#eec06e" stroke="#9b713c"><path d="M19 105h19v10q0 12-9 12t-10-12Z" /><path d="M19 108h-7q-3 14 11 13m15-13h7q3 14-11 13M29 127v8m-8 0h16" /><circle cx="29" cy="110" r="5" fill="#fff0b3" /></g> : null}
    {path === "honor" && a ? <g stroke="#b992c9" fill="#f0d4ed"><circle cx="128" cy="110" r="12" /><path d="M121 106q0-4 5-4" stroke="white" /></g> : null}
    {path === "valorant" && a ? <path d="M21 121q19 9 29-4m60 8q17 1 25-8" stroke="#a4e5df" strokeWidth="3" /> : null}
    {path === "lol" && a ? <g stroke="#67bbc9"><circle cx="125" cy="108" r="14" fill="#b7f0ed" /><path d="M117 108q8-15 15-1t-15 1" stroke="#f1ffff" /></g> : null}
    {path === "nexus" && a ? <path d="M27 117a8 8 0 1 0 8 11 7 7 0 0 1-8-11" fill="#f5dcaa" stroke="#a596d6" /> : null}
    {e ? <g stroke={path === "nba" ? "#dab36f" : "#bfaddf"}><path d="m57 143 23 5 23-5" /><path d="m76 145 4-5 4 5-4 5Z" fill="#fff2c7" /></g> : null}
    {/* A small rank seal changes after every successful evolution, even between milestones. */}
    {stage >= 2 ? <g data-evolution-rank={stage}><rect x="113" y="133" width="25" height="15" rx="6" fill="#fff9e9" stroke="#a39887" strokeWidth="1" /><text x="125.5" y="144" textAnchor="middle" fill="#5a5260" stroke="none" fontSize="10" fontWeight="700" fontFamily="sans-serif">{stage}</text></g> : null}
  </g>;
  return <g data-route-progress="back" fill="none" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2">
    {path === "eva" ? <g stroke="#edb470">{b ? <path d="M80 12 125 31 144 77 125 122 80 143 35 122 16 77 35 31Z" opacity=".7" /> : null}{d ? <path d="m80 3 53 23 23 51-23 52-53 24-53-24L4 77l23-51Z" strokeWidth="3" opacity=".6" /> : null}{e ? <path d="m16 46 12 8m105 0 11-8M12 105l14-5m108 0 14 5" stroke="#c7fc75" strokeWidth="4" /> : null}</g> : null}
    {path === "blade_soul" ? <g stroke="#508e9b" fill="#def9f0">{(b ? [-1, 1] : []).map((side) => <path key={side} transform={`translate(${80 + side * 48} 78) rotate(${side * 27})`} d="m0-57 5 14-3 48h5v4H2v12h-4V9h-5V5h5l-3-48Z" />)}{c ? <path d="m71 14 9-11 9 11-7 48h-4Z" fill="#a9ddd5" /> : null}{d ? <path d="M16 114q17 32 64 32t64-32M24 122q0-24 16-32" stroke="#86c9bb" /> : null}{e ? <path d="m17 38 7-12 4 15-5 31Zm122 0-7-12-4 15 5 31Z" /> : null}</g> : null}
    {path === "dnf" ? <g stroke="#cb6c80">{b ? <path d="M45 131q-29-15-16-43-1 17 15 13m63 29q26-7 30-29" strokeWidth="5" /> : null}{d ? <path d="m14 73 16 13m-16 5 13 5m116-53-9 12m12 0-10 11" stroke="#f0c182" strokeWidth="4" /> : null}{e ? <path d="M21 132q59 23 118 0" strokeWidth="5" /> : null}</g> : null}
    {path === "nba" ? <g stroke="#cead73">{d ? <><path d="m24 19 26 107M136 19l-26 107" stroke="#edd7a3" strokeWidth="11" opacity=".4" /><path d="M17 141h126m-119-5 18-10m94 10-18-10" /></> : null}{e ? <g fill="#e9bf72" strokeWidth="1"><path d="m34 23 3 5 6 1-4 4 1 6-6-3-5 3 1-6-4-4 6-1Z" /><path d="m123 23 3 5 6 1-4 4 1 6-6-3-5 3 1-6-4-4 6-1Z" /></g> : null}</g> : null}
    {path === "honor" ? <g stroke="#ba91c6">{b ? <ellipse cx="80" cy="86" rx="62" ry="61" strokeWidth="4" strokeDasharray="65 12" opacity=".55" /> : null}{c ? <path d="M15 109q50 48 126-16M22 116q14-26 25-6" stroke="#e5b7ce" strokeWidth="5" /> : null}{d ? <g fill="#d9c4ec"><circle cx="27" cy="53" r="9" /><circle cx="135" cy="71" r="7" /><circle cx="115" cy="25" r="6" /></g> : null}{e ? <path d="M18 139q-4-14 8-20m-3 11-11-6m126 15q4-14-8-20m3 11 11-6" stroke="#8cbaa0" strokeWidth="4" /> : null}</g> : null}
    {path === "valorant" ? <g stroke="#74b8c1" fill="#e1ffff">{b ? <path d="m17 86 5-24 4 21-4 9Z" /> : null}{c ? <path d="m80 7 4 18-4 11-4-11Zm62 61 4 18-4 11-4-11Z" /> : null}{d ? <path d="M17 54Q2 122 75 140m70-73q5-30-20-43" stroke="#8ed7d3" strokeWidth="4" fill="none" /> : null}{e ? <path d="m7 107 19 7m107-75 18 4M37 141l15-8" stroke="#5eaabd" strokeWidth="3" /> : null}</g> : null}
    {path === "lol" ? <g stroke="#b4a1b7" strokeWidth="1.35">
      <g transform="translate(80 0) scale(.84 1) translate(-80 0)">{[-4,4,-3,3,-2,2,-1,1,0].map((index) => <g key={index} transform={`translate(80 126) rotate(${index * (e ? 15 : d ? 14 : c ? 12 : b ? 10 : a ? 9 : 8)}) scale(${e ? 1.02 : d ? .98 : c ? .94 : b ? .86 : a ? .79 : .72}) translate(-80 -126)`}>
        <path d="M76 128C48 113 43 64 66 29c-5 31 27 43 26 69q1 20-16 30Z" fill={index % 2 ? "#eee1ee" : "#fff6ef"} />
        <path d="M66 29c-4 18 5 33 13 43q-16-5-20-13" fill="#ddd4e8" stroke="none" />
        <path d="M77 115q-17-21-14-41" fill="none" stroke="#e2cfdc" />
      </g>)}</g>
      {b ? <g stroke="#84c6db" fill="#bbe9fa"><path d="M18 85q-9-10 3-23-3 10 5 13 4 13-8 10Zm124 0q-9-10 3-23-3 10 5 13 4 13-8 10Z" /></g> : null}
      {e ? <path d="M9 115q71 47 142 0" stroke="#99cce1" strokeWidth="4" fill="none" /> : null}
    </g> : null}
    {path === "nexus" ? <g stroke="#c3abeb">{b ? <path d="m42 91-26-28 5 30-11 5 34 20m74-27 26-28-5 30 11 5-34 20" fill="#8274b1" /> : null}{c ? <ellipse cx="80" cy="79" rx="67" ry="43" transform="rotate(30 80 79)" /> : null}{d ? <path d="m22 39 31-23 59 3 25 27m-84-30 27 18 32-15" strokeDasharray="3 4" /> : null}{e ? <circle cx="80" cy="80" r="74" strokeWidth="3" strokeDasharray="1 13" /> : null}</g> : null}
  </g>;
}
