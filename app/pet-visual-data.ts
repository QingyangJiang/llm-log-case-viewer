/** Visual catalog shared by the CaseLens wardrobe and the native desktop pet. */
export type PetColor = "lime" | "aqua" | "peach" | "lavender" | "sky" | "coral" | "gold" | "midnight" | "rose" | "jade" | "violet" | "sunset" | "ice" | "fuchsia" | "emerald" | "azure" | "ruby" | "pearl" | "aurora" | "cosmos";
export type PetFashionSlot = "headwear" | "outfit" | "outerwear" | "footwear" | "handheld";
export type PetRarity = "common" | "uncommon" | "rare" | "epic" | "legendary";
export type PetFashionItem = { id: string; name: string; slot: PetFashionSlot; slot_name: string; symbol: string; theme: string; theme_name: string; level: number; rarity: PetRarity; primary: string; secondary: string };
export type PetEvolutionPath = "" | "starlight" | "guardian" | "forest" | "storm" | "ocean" | "ember" | "cloud" | "pixel" | "wonky" | "eva" | "blade_soul" | "dnf" | "nba" | "honor" | "valorant" | "lol" | "nexus";

export const PET_COLORS: { id: PetColor; label: string; value: string; level: number }[] = [
  { id: "lime", label: "青柠", value: "#d9ff78", level: 1 },
  { id: "aqua", label: "薄荷", value: "#9de8dc", level: 2 },
  { id: "peach", label: "蜜桃", value: "#ffc7b8", level: 3 },
  { id: "lavender", label: "薰衣草", value: "#cbbcff", level: 4 },
  { id: "sky", label: "晴空", value: "#9fd7ff", level: 5 },
  { id: "coral", label: "珊瑚", value: "#ff9c91", level: 6 },
  { id: "gold", label: "鎏金", value: "#ffda68", level: 8 },
  { id: "midnight", label: "星夜", value: "#7e88b8", level: 10 },
  { id: "rose", label: "玫瑰汽水", value: "#ff8fb8", level: 12 },
  { id: "jade", label: "翡翠", value: "#63e6ad", level: 15 },
  { id: "violet", label: "紫晶", value: "#9b7cff", level: 18 },
  { id: "sunset", label: "落日橘", value: "#ff9a5c", level: 20 },
  { id: "ice", label: "冰晶", value: "#d8f3ff", level: 24 },
  { id: "fuchsia", label: "绮丽洋红", value: "#f16cff", level: 28 },
  { id: "emerald", label: "极光绿", value: "#46d997", level: 32 },
  { id: "azure", label: "电光蓝", value: "#4fb3ff", level: 36 },
  { id: "ruby", label: "红宝石", value: "#ef476f", level: 40 },
  { id: "pearl", label: "月白珍珠", value: "#f7efe5", level: 45 },
  { id: "aurora", label: "极昼青", value: "#77f2c2", level: 48 },
  { id: "cosmos", label: "宇宙蓝紫", value: "#5961d8", level: 50 },
];
export const PET_FASHION_SLOTS: Record<PetFashionSlot, { label: string; symbol: string }> = {
  headwear: { label: "发型头饰", symbol: "♛" },
  outfit: { label: "连衣套装", symbol: "♢" },
  outerwear: { label: "外套披风", symbol: "⌁" },
  footwear: { label: "鞋袜", symbol: "⌄" },
  handheld: { label: "手持物", symbol: "✦" },
};
export const PET_FASHION_THEMES = [
  { id: "academy", name: "森系学院", subtitle: "新生报到", level: 1, primary: "#537861", secondary: "#f0d7a1", pieces: { headwear: ["学院贝雷帽", "◆"], outfit: ["格纹学院装", "▦"], outerwear: ["深绿短斗篷", "⌁"], footwear: ["棕色乐福鞋", "⌄"], handheld: ["课程手册", "▤"] } },
  { id: "berry", name: "草莓甜心", subtitle: "午后茶会", level: 3, primary: "#ef7694", secondary: "#fff0d5", pieces: { headwear: ["莓果奶油帽", "●"], outfit: ["草莓泡泡裙", "♥"], outerwear: ["奶油针织衫", "≈"], footwear: ["糖霜圆头鞋", "⌄"], handheld: ["莓果小蛋糕", "♧"] } },
  { id: "cloud", name: "云朵梦游", subtitle: "软绵睡衣", level: 5, primary: "#9cbbe7", secondary: "#f7f5ff", pieces: { headwear: ["月亮睡帽", "☾"], outfit: ["云朵连体衣", "☁"], outerwear: ["星星小毯子", "✦"], footwear: ["绒绒拖鞋", "⌄"], handheld: ["晚安抱枕", "○"] } },
  { id: "sailor", name: "海盐航行", subtitle: "晴日出海", level: 8, primary: "#3979a8", secondary: "#f4efe3", pieces: { headwear: ["海风水手帽", "△"], outfit: ["蓝白水手服", "≋"], outerwear: ["航海短披肩", "⌁"], footwear: ["甲板短靴", "⌄"], handheld: ["迷你望远镜", "◎"] } },
  { id: "forest", name: "森林茶会", subtitle: "花园来客", level: 10, primary: "#55966b", secondary: "#f2d79e", pieces: { headwear: ["花叶软帽", "♧"], outfit: ["苔绿茶会裙", "❀"], outerwear: ["藤蔓小披肩", "⌁"], footwear: ["蘑菇系带鞋", "⌄"], handheld: ["铃兰花篮", "❁"] } },
  { id: "starlight", name: "星河礼服", subtitle: "银河舞会", level: 12, primary: "#6760b8", secondary: "#f3d879", pieces: { headwear: ["星月发冠", "✦"], outfit: ["银河礼服", "⋆"], outerwear: ["流星薄纱", "⌁"], footwear: ["星尘舞鞋", "⌄"], handheld: ["星轨手杖", "☄"] } },
  { id: "detective", name: "侦探事务所", subtitle: "谜案追踪", level: 15, primary: "#6e5948", secondary: "#d6b777", pieces: { headwear: ["猎鹿侦探帽", "◇"], outfit: ["线索调查装", "▥"], outerwear: ["长款风衣", "⌁"], footwear: ["寻迹皮靴", "⌄"], handheld: ["线索放大镜", "◉"] } },
  { id: "neon", name: "霓虹未来", subtitle: "夜城巡游", level: 18, primary: "#4f63d9", secondary: "#55f0d2", pieces: { headwear: ["全息耳罩", "Ω"], outfit: ["霓虹机能装", "▦"], outerwear: ["光轨夹克", "⌁"], footwear: ["悬浮跑鞋", "⌄"], handheld: ["像素终端", "▣"] } },
  { id: "royal", name: "月桂王庭", subtitle: "花冠典礼", level: 22, primary: "#8b5b99", secondary: "#efd785", pieces: { headwear: ["月桂宝冠", "♛"], outfit: ["王庭礼仪服", "♕"], outerwear: ["紫金大披风", "⌁"], footwear: ["典礼长靴", "⌄"], handheld: ["月桂权杖", "†"] } },
  { id: "aurora", name: "极光雪国", subtitle: "冰晶庆典", level: 28, primary: "#70b9c7", secondary: "#eefcff", pieces: { headwear: ["冰晶绒帽", "❉"], outfit: ["极光雪衣", "❄"], outerwear: ["北境绒披风", "⌁"], footwear: ["踏雪毛靴", "⌄"], handheld: ["雪花提灯", "✧"] } },
  { id: "phoenix", name: "赤焰华服", subtitle: "凤凰巡礼", level: 36, primary: "#d65343", secondary: "#ffc857", pieces: { headwear: ["赤金凤冠", "♨"], outfit: ["流火华裳", "火"], outerwear: ["凤凰羽衣", "⌁"], footwear: ["踏焰云履", "⌄"], handheld: ["赤羽团扇", "◒"] } },
  { id: "cosmos", name: "宇宙歌剧", subtitle: "终幕星穹", level: 45, primary: "#343b91", secondary: "#e777df", pieces: { headwear: ["星穹冠冕", "✺"], outfit: ["宇宙歌剧服", "∞"], outerwear: ["星云长披风", "⌁"], footwear: ["引力星靴", "⌄"], handheld: ["天体仪", "◎"] } },
] as const;
export const PET_FASHION_CATALOG: PetFashionItem[] = PET_FASHION_THEMES.flatMap((theme) => (Object.entries(PET_FASHION_SLOTS) as [PetFashionSlot, { label: string; symbol: string }][]).map(([slot, slotInfo]) => {
  const [name, symbol] = theme.pieces[slot];
  const level = theme.level;
  const rarity: PetRarity = level >= 40 ? "legendary" : level >= 25 ? "epic" : level >= 12 ? "rare" : level >= 5 ? "uncommon" : "common";
  return { id: `fashion-${theme.id}-${slot}`, name, slot, slot_name: slotInfo.label, symbol, theme: theme.id, theme_name: theme.name, level, rarity, primary: theme.primary, secondary: theme.secondary };
}));
export const PET_EVOLUTION_PATHS: Record<Exclude<PetEvolutionPath, "">, { name: string; motif: string; traits: string[][]; tone: string; hidden?: boolean }> = {
  starlight: { name: "星辉灵兽", motif: "✦", traits: [["星尘额纹", "新月耳尖", "彗星小角"], ["月光羽翼", "星轨尾焰", "银河披风"], ["星环冠冕", "极光领域", "星核辉光"], ["群星脉络", "超新星尾迹", "天穹结晶"], ["星海共鸣", "永昼星环", "宇宙心核"], ["星神投影", "万象星幕", "永恒辉光"]], tone: "璀璨" },
  guardian: { name: "守护机甲", motif: "◆", traits: [["合金耳甲", "战术目镜", "棱镜面罩"], ["折叠钢翼", "推进尾翼", "护盾肩甲"], ["量子核心", "冠军冠冕", "脉冲力场"], ["轨道装甲", "光束翼阵", "重力护盾"], ["星舰核心", "堡垒领域", "超导王冠"], ["终焉机铠", "天基阵列", "不灭能源"]], tone: "坚毅" },
  forest: { name: "森灵幻兽", motif: "♧", traits: [["新芽鹿角", "苔藓耳尖", "花蕾额纹"], ["叶脉羽翼", "花藤披风", "蒲公英尾"], ["萤火光环", "古树冠冕", "四季领域"], ["灵鹿枝冠", "雨林结界", "蘑菇星灯"], ["世界树心", "百花圣环", "万物低语"], ["森神化身", "四季轮转", "生命洪流"]], tone: "温柔" },
  storm: { name: "风暴精灵", motif: "ϟ", traits: [["闪电耳羽", "雷云额纹", "电光小角"], ["疾风羽翼", "旋风尾环", "雷霆披风"], ["风眼冠冕", "暴雨领域", "蓝电核心"], ["雷暴羽阵", "闪击足环", "积雨云甲"], ["极昼雷核", "天罚光环", "飓风结界"], ["雷神化身", "万钧天幕", "永动风眼"]], tone: "迅捷" },
  ocean: { name: "潮汐幻灵", motif: "≈", traits: [["珊瑚耳鳍", "珍珠额珠", "浪花尾尖"], ["潮汐披风", "水晶鳍翼", "泡泡光环"], ["深海冠冕", "鲸歌领域", "海蓝心核"], ["洋流翼阵", "月潮鳞甲", "海沟辉石"], ["七海圣环", "潮汐王座", "深蓝结界"], ["海神投影", "无尽洋流", "深渊星光"]], tone: "澄澈" },
  ember: { name: "焰心灵狐", motif: "△", traits: [["火苗耳尖", "暖阳额纹", "炭火尾尖"], ["熔岩披风", "焰羽双翼", "火花足环"], ["烈阳冠冕", "赤焰领域", "熔火心核"], ["凤凰尾羽", "日珥翼阵", "曜石战甲"], ["太阳圣环", "焚天结界", "赤金王座"], ["火神化身", "恒星熔炉", "不灭真焰"]], tone: "炽热" },
  cloud: { name: "云梦团子", motif: "☁", traits: [["棉云耳朵", "彩虹额纹", "雨滴尾巴"], ["软云翅膀", "晚霞披风", "风铃足环"], ["晴空冠冕", "梦境领域", "虹光心核"], ["层云软甲", "晨曦翼阵", "雷雨铃铛"], ["九霄圣环", "幻梦结界", "天空王座"], ["云神化身", "万里晴空", "长梦不醒"]], tone: "软绵" },
  pixel: { name: "像素精怪", motif: "▦", traits: [["方块耳尖", "扫描额纹", "光标尾巴"], ["数据翅膀", "代码披风", "缓存光环"], ["像素冠冕", "矩阵领域", "算力核心"], ["量子像素", "递归翼阵", "霓虹装甲"], ["无限循环环", "协议王座", "虚拟结界"], ["数字神格", "全域矩阵", "永恒在线"]], tone: "赛博" },
  wonky: { name: "歪歪异变体", motif: "≋", traits: [["参差尖牙", "皱皱触角", "大小眼花纹"], ["斑驳小翅膀", "歪斜尾鳍", "补丁披风"], ["倾斜纸冠", "毛边光圈", "咕嘟气泡场"], ["打结尾巴", "漏气翼阵", "反向护目镜"], ["掉漆王座", "卡顿领域", "吱呀心核"], ["究极毛边", "歪星圣环", "混沌咕嘟"]], tone: "有点难看" },
  eva: { name: "EVA · 同步机体", motif: "◈", traits: [["紫绿装甲", "单角头甲", "同步目镜"], ["拘束肩甲", "核心胸灯", "脐带电缆"], ["AT 力场", "八边屏障", "领域投影"], ["核心觉醒", "装甲辉光", "觉醒核心"], ["领域扩张", "力场共鸣", "八边领域"], ["同步突破", "核心共鸣", "机体觉醒"]], tone: "同步" },
  blade_soul: { name: "剑灵 · 御剑灵兽", motif: "剑", traits: [["灵族长耳", "青玉飞剑", "灵剑剑穗"], ["流云披帛", "玉佩腰带", "青锋护手"], ["双剑护身", "灵气流转", "剑穗飘带"], ["御剑剑阵", "剑气环绕", "灵剑共鸣"], ["流云剑气", "剑阵展开", "剑心护持"], ["剑心通明", "飞剑齐鸣", "灵气归一"]], tone: "凌厉" },
  dnf: { name: "DNF · 深渊勇者", motif: "✥", traits: [["银发剑士", "鬼手印记", "冒险长剑"], ["鬼手锁链", "皮革护甲", "剑柄护手"], ["血气觉醒", "锁链护腕", "血色剑气"], ["巨剑锋芒", "觉醒剑痕", "阿拉德徽记"], ["剑痕爆发", "鬼手辉光", "巨剑重斩"], ["冒险者荣誉", "阿拉德勇士", "觉醒锋芒"]], tone: "觉醒" },
  nba: { name: "NBA · 全明星球王", motif: "●", traits: [["新秀球衣", "运动发带", "圆头球鞋"], ["运动护臂", "吸汗护腕", "训练队服"], ["全明星徽章", "球衣金边", "比赛用球"], ["冠军奖杯", "夺冠纪念", "球场荣誉"], ["主场聚光", "球场边线", "全明星之夜"], ["传奇球星", "荣誉金星", "冠军纪念章"]], tone: "热血" },
  honor: { name: "王者 · 峡谷传说", motif: "♜", traits: [["入梦绒耳", "梦纹额饰", "信物吊坠"], ["梦力泡泡", "幻梦绒毛", "寻梦足迹"], ["梦境护盾", "梦力流转", "绒耳灵光"], ["梦境环游", "泡泡轨迹", "幻梦涟漪"], ["幻梦森林", "寻梦花叶", "梦泡簇拥"], ["寻梦之旅", "梦力共鸣", "入梦之灵"]], tone: "荣耀" },
  valorant: { name: "VALORANT · 战术特工", motif: "V", traits: [["白发束髻", "青蓝战衣", "战术手套"], ["乘风起势", "轻装护臂", "风刃护手"], ["浮空飞刃", "上升气流", "风势环绕"], ["五刃齐发", "逐风轨迹", "精准飞刃"], ["疾风掠影", "风流交错", "机动轨迹"], ["王牌时刻", "飞刃齐鸣", "疾风纪念章"]], tone: "精准" },
  lol: { name: "LOL · 符文传奇", motif: "◐", traits: [["灵狐双耳", "九尾绒毛", "面颊狐纹"], ["灵魂宝珠", "红白灵衣", "金边腰饰"], ["狐火环绕", "灵珠辉光", "灵魂流光"], ["灵魄突袭", "狐尾流转", "灵火足迹"], ["九尾舒展", "灵魂涟漪", "狐火共鸣"], ["灵魂共鸣", "灵狐辉光", "九尾流光"]], tone: "传奇" },
  nexus: { name: "终焉 · 次元观测者", motif: "?", traits: [["月相额纹", "星河绒羽", "观测尾光"], ["月相流转", "弦月伴星", "月光轨迹"], ["星羽展开", "绒羽流光", "次元羽翼"], ["双重星轨", "星环交汇", "观测星体"], ["星图浮现", "星座连线", "星幕绘卷"], ["次元观测", "观测者印记", "群星共鸣"]], tone: "隐藏", hidden: true },
};
