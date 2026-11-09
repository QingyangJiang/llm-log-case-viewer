/** Character names, progression and illustration palette shared by web and desktop. */
export const CROSSOVER_ROUTES = {
  wukong: {
    name: "黑神话 · 悟空", motif: "悟", tone: "齐天",
    palette: { light: "#f7ddb2", base: "#9a7449", dark: "#3c3028", accent: "#d2a45b", soft: "#f5ecda", caption: "天命行者 · 赤金如意" },
    milestones: ["天命行者", "葫芦行囊", "赤金战意", "凤翅齐天", "腾云入圣", "大圣归来"],
    traits: [["如意金箍棒", "灵猴面相", "玄金战甲"], ["酒葫芦", "行者飘带", "金纹束带"], ["金甲护身", "如意棍花", "赤金战意"], ["凤翅紫金冠", "双翎长羽", "齐天冠冕"], ["筋斗祥云", "云海环绕", "踏云金光"], ["大圣归来", "金箍法相", "如意无边"]],
  },
  nezha: {
    name: "黑神话风 · 哪吒", motif: "莲", tone: "赤莲",
    palette: { light: "#f8cbb4", base: "#b54848", dark: "#4c2938", accent: "#e47850", soft: "#f9e9df", caption: "原创暗黑神话风 · 赤莲少年" },
    milestones: ["赤莲少年", "混天绫舞", "乾坤金轮", "风火双轮", "莲焰盛放", "六臂法相"],
    traits: [["双髻朱绳", "赤莲额印", "火尖枪"], ["混天绫", "朱绫回舞", "赤金绑带"], ["乾坤圈", "金轮护身", "莲纹护腕"], ["风火轮", "双轮踏焰", "焰尾流光"], ["赤莲法座", "莲焰盛放", "火莲羽瓣"], ["六臂法相", "莲心不灭", "破厄金光"]],
  },
  aobing: {
    name: "黑神话风 · 敖丙", motif: "龙", tone: "沧澜",
    palette: { light: "#f2fcff", base: "#7dbacc", dark: "#294b68", accent: "#76cde1", soft: "#e5f5fa", caption: "原创暗黑神话风 · 冰龙公子" },
    milestones: ["冰龙公子", "寒玉龙鳞", "冰晶长枪", "龙尾沧浪", "霜龙环身", "四海龙吟"],
    traits: [["冰蓝长发", "玉色龙角", "沧海长枪"], ["寒玉龙鳞", "鳞甲悬玉", "冰晶护身"], ["冰晶枪锋", "寒霜结晶", "蓝玉枪阵"], ["龙尾沧浪", "踏浪云履", "海潮回卷"], ["霜龙环身", "寒龙显形", "冰鳞长龙"], ["四海龙吟", "龙珠共鸣", "苍海龙域"]],
  },
  doraemon: {
    name: "哆啦A梦", motif: "铃", tone: "百宝",
    palette: { light: "#e6faff", base: "#42b2dc", dark: "#246c96", accent: "#f1bd54", soft: "#e7f7ff", caption: "蓝色圆梦伙伴 · 四次元口袋" },
    milestones: ["口袋伙伴", "铜锣烧时刻", "竹蜻蜓起飞", "任意门启程", "时光机旅行", "星空百宝袋"],
    traits: [["红鼻蓝猫", "金色铃铛", "四次元口袋"], ["铜锣烧", "点心纸袋", "甜甜笑颜"], ["竹蜻蜓", "轻风螺旋", "飞行小帽"], ["粉色任意门", "任意门钥匙", "快乐启程"], ["时光机", "时空仪表", "旅行座舱"], ["百宝星空", "未来星环", "圆梦之旅"]],
  },
  furina: {
    name: "水神 · 芙宁娜", motif: "水", tone: "水华",
    palette: { light: "#f0f6ff", base: "#739bda", dark: "#304779", accent: "#80cde8", soft: "#ebf2ff", caption: "芙宁娜灵感 · 水色歌剧" },
    milestones: ["水色独舞", "海沫礼赞", "沙龙来客", "众水巡游", "歌剧开幕", "水华终章"],
    traits: [["蓝白礼帽", "水色异瞳", "歌剧燕尾服"], ["海沫水滴", "水纹礼赞", "蓝晶胸针"], ["沙龙小章鱼", "水灵来客", "水泡伴舞"], ["螃蟹骑士", "海马使者", "众水巡游"], ["歌剧帷幕", "聚光水幕", "水色舞台"], ["水华终章", "礼赞之冠", "众水回响"]],
  },
  yae_miko: {
    name: "原神 · 八重神子", motif: "樱", tone: "鸣樱",
    palette: { light: "#ffe3e7", base: "#db9bad", dark: "#654560", accent: "#c19bdb", soft: "#fff0f3", caption: "八重神子灵感 · 樱色鸣雷" },
    milestones: ["鸣樱巫女", "御币樱舞", "杀生樱现", "三樱结阵", "天狐显影", "神樱眷顾"],
    traits: [["粉色狐耳", "白赤巫女服", "紫电神之眼"], ["御币幡纸", "樱花回舞", "朱绳神铃"], ["杀生樱", "紫电狐灯", "樱枝雷纹"], ["三樱结阵", "狐灯齐鸣", "雷樱连线"], ["天狐显影", "五尾灵光", "狐灵守候"], ["神樱眷顾", "樱雷法环", "鸣神御守"]],
  },
};

export type CrossoverRoute = keyof typeof CROSSOVER_ROUTES;
export function isCrossoverRoute(path: string): path is CrossoverRoute {
  return Object.prototype.hasOwnProperty.call(CROSSOVER_ROUTES, path);
}

/** Retired routes reserve the corresponding replacement until their owner loads it. */
export const RETIRED_ROUTE_REPLACEMENTS: Record<string, CrossoverRoute> = {
  phantom_soul: "wukong", phantom_zuoshang: "aobing",
  phantom_xiaokui: "nezha", phantom_xianzhe: "yae_miko",
};
export function replacementPetRoute(path: string): string {
  return RETIRED_ROUTE_REPLACEMENTS[path] ?? path;
}
