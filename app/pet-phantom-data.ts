/** Character-inspired companions; milestone names are original CaseLens designs. */
export const PHANTOM_ROUTES = {
  phantom_soul: {
    name: "影之刃零 · 魂", motif: "刃", tone: "孤锋",
    palette: { light: "#a5b8bb", base: "#384750", dark: "#202831", accent: "#d65e55", soft: "#f1e9e3", caption: "魂灵感 · 墨衣赤刃" },
    milestones: ["墨衣孤锋", "赤巾猎风", "双刃出鞘", "残影逐月", "墨羽长氅", "一刃破局"],
    traits: [["墨衣剑客", "赤刃锋芒", "束发红绳"], ["赤巾猎风", "旧铜刀镡", "绑带护腕"], ["双刃出鞘", "交错剑锋", "赤纹剑鞘"], ["残影逐月", "墨痕刀弧", "疾行衣摆"], ["墨羽长氅", "赤金刀纹", "回风披带"], ["一刃破局", "孤锋剑意", "赤月刀光"]],
  },
  phantom_zuoshang: {
    name: "影之刃零 · 左殇", motif: "锋", tone: "藏锋",
    palette: { light: "#f5edda", base: "#a4967c", dark: "#363638", accent: "#d6b76e", soft: "#f6f0df", caption: "左殇灵感 · 紫锋金芒" },
    milestones: ["藏锋剑客", "鎏金肩甲", "剑气悬锋", "三剑成阵", "游龙剑势", "金阙剑域"],
    traits: [["紫锋长剑", "束冠墨发", "金纹武袍"], ["鎏金肩甲", "云纹腰封", "垂玉剑穗"], ["剑气悬锋", "金芒护刃", "悬剑护身"], ["三剑成阵", "交织剑气", "御刃之势"], ["游龙剑势", "金绸剑光", "龙纹披帛"], ["金阙剑域", "六锋齐鸣", "藏锋归一"]],
  },
  phantom_xiaokui: {
    name: "影之刃零 · 沐小葵", motif: "葵", tone: "灵巧",
    palette: { light: "#e6f1e6", base: "#679b8a", dark: "#344b47", accent: "#ce7b79", soft: "#eef3e8", caption: "沐小葵灵感 · 青衫双卫" },
    milestones: ["青衫小葵", "流袖系铃", "玉卫相随", "铁卫同行", "红绫牵机", "双卫护心"],
    traits: [["青衫少女", "朱绳发结", "银叶发簪"], ["流袖系铃", "青玉腰佩", "锦绣裙摆"], ["玉卫相随", "玉色机关", "轻灵护卫"], ["铁卫同行", "重甲机关", "双卫守候"], ["红绫牵机", "绫带回环", "机关共鸣"], ["双卫护心", "银枝花冠", "青绫环舞"]],
  },
  phantom_xianzhe: {
    name: "影之刃零 · 弦者", motif: "弦", tone: "幽弦",
    palette: { light: "#eee4db", base: "#946d77", dark: "#3f3541", accent: "#c7a66c", soft: "#f3e9eb", caption: "弦者灵感 · 琵琶幽音" },
    milestones: ["抱月幽弦", "锦袖垂音", "弦波初起", "三叠回响", "朱弦织境", "月下终曲"],
    traits: [["怀抱琵琶", "墨发朱绳", "木偶关节"], ["锦袖垂音", "金纹琴轸", "绣边长裙"], ["弦波初起", "金线回声", "幽音环绕"], ["三叠回响", "弦阵展开", "琴纹流光"], ["朱弦织境", "绯色琴丝", "回声垂幕"], ["月下终曲", "弦月共鸣", "余音不散"]],
  },
};

export type PhantomRoute = keyof typeof PHANTOM_ROUTES;

export function isPhantomRoute(path: string): path is PhantomRoute {
  return Object.prototype.hasOwnProperty.call(PHANTOM_ROUTES, path);
}
