from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match in {path}, found {count}")
    path.write_text(text.replace(old, new, 1))


def replace_regex(path: Path, pattern: str, replacement: str, label: str) -> None:
    text = path.read_text()
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one regex match in {path}, found {count}")
    path.write_text(updated)


page = ROOT / "app/page.tsx"
backend = ROOT / "backend/app/main.py"
css = ROOT / "app/globals.css"
readme = ROOT / "README.md"

replace_once(
    page,
    'type PetEvolutionEvent = { at: string; type?: "gift"; spent: number; guaranteed?: boolean; success: boolean; stage: number; path: PetEvolutionPath; trait: string; traits?: string[]; critical?: boolean; success_rate?: number; pity_after?: number; amount?: number; sender?: string; skill?: PetSkill | null };',
    'type PetEvolutionEvent = { at: string; type?: "gift" | "reroute"; spent: number; guaranteed?: boolean; success: boolean; stage: number; path: PetEvolutionPath; trait: string; traits?: string[]; critical?: boolean; success_rate?: number; pity_after?: number; amount?: number; sender?: string; previous_path?: PetEvolutionPath; route_reset?: boolean; skill?: PetSkill | null };',
    "extend PetEvolutionEvent",
)

new_local_evolve = r'''function evolveLocalPet(profile: PetProfile, spend: 1 | 5) {
  const echo = profile.active_skills.includes("evolution_echo") ? profile.skills.find((item) => item.id === "evolution_echo")?.level ?? 0 : 0;
  const steady = profile.active_skills.includes("steady_heart") ? profile.skills.find((item) => item.id === "steady_heart")?.level ?? 0 : 0;
  const successRate = Math.min(45, 10 + echo + Math.min(30, profile.evolution_pity * (2 + steady)));
  const success = spend === 5 || petRandomInt(100) < successRate;
  const routeReset = spend === 5 && Boolean(profile.evolution_path) && profile.evolution_stage > 0;
  const previousPath = routeReset ? profile.evolution_path : "";
  let path = profile.evolution_path;
  let variant = profile.evolution_variant;
  let traits = [...profile.evolution_traits];
  let stage = profile.evolution_stage;
  const wonTraits: string[] = [];
  let critical = false;
  let skills = [...profile.skills];
  const activeSkills = [...profile.active_skills];
  let awakenedSkill: PetSkill | null = null;
  if (success) {
    if (routeReset) {
      const rerollPool = PET_EVOLUTION_PATH_LOTTERY.filter((candidate) => candidate !== previousPath);
      path = rerollPool[petRandomInt(rerollPool.length)];
      stage = 0;
      traits = [];
    } else if (!path) {
      path = PET_EVOLUTION_PATH_LOTTERY[petRandomInt(PET_EVOLUTION_PATH_LOTTERY.length)];
    }
    critical = routeReset ? false : petRandomInt(100) < 12;
    const stageGain = routeReset ? 1 : critical ? 2 : 1;
    for (let offset = 0; offset < stageGain; offset += 1) {
      const nextStage = stage + offset;
      const pools = PET_EVOLUTION_PATHS[path];
      const traitPool = pools.traits[Math.min(Math.floor(nextStage / 2), pools.traits.length - 1)];
      let trait = traitPool[petRandomInt(traitPool.length)];
      if (nextStage >= pools.traits.length * 2) trait = `${trait} · 星环${nextStage - pools.traits.length * 2 + 1}`;
      wonTraits.push(trait);
      traits.push(trait);
    }
    traits = traits.slice(-24);
    stage += stageGain;
    variant = petRandomInt(8);
    const definition = PET_SKILL_DEFINITIONS[petRandomInt(PET_SKILL_DEFINITIONS.length)];
    skills = skills.length ? skills : PET_SKILL_DEFINITIONS.map((item) => ({ ...item, level: 0, active: false }));
    skills = skills.map((item) => item.id === definition.id ? { ...item, level: Math.min(5, item.level + 1) } : item);
    awakenedSkill = skills.find((item) => item.id === definition.id) ?? null;
    if (!activeSkills.includes(definition.id) && activeSkills.length < 3) activeSkills.push(definition.id);
    skills = skills.map((item) => ({ ...item, active: activeSkills.includes(item.id) }));
  }
  const historyTrait = routeReset && success ? `换路线 · ${wonTraits.join(" / ")}` : wonTraits.join(" / ");
  const event: PetEvolutionEvent = {
    at: new Date().toISOString(),
    ...(routeReset ? { type: "reroute" as const, previous_path: previousPath, route_reset: true } : {}),
    spent,
    guaranteed: spend === 5,
    success,
    stage,
    path,
    trait: historyTrait,
    traits: wonTraits,
    critical,
    success_rate: spend === 5 ? 100 : successRate,
    pity_after: success ? 0 : Math.min(20, profile.evolution_pity + 1),
    skill: awakenedSkill,
  };
  return {
    success,
    trait: wonTraits.join(" / "),
    critical,
    skill: awakenedSkill,
    route_reset: routeReset && success,
    previous_path: previousPath,
    profile: normalizedPetProfile({
      ...profile,
      evolution_chances: profile.evolution_chances - spend,
      evolution_stage: stage,
      evolution_path: path,
      evolution_variant: variant,
      evolution_traits: traits,
      evolution_history: [event, ...profile.evolution_history].slice(0, 50),
      evolution_pity: success ? 0 : Math.min(20, profile.evolution_pity + 1),
      evolution_success_rate: success ? 10 : Math.min(45, 10 + (Math.min(20, profile.evolution_pity + 1) * (2 + steady)) + echo),
      skills,
      active_skills: activeSkills,
    }),
  };
}

function activePetSkillLevel'''
replace_regex(
    page,
    r'function evolveLocalPet\(profile: PetProfile, spend: 1 \| 5\) \{.*?\n\}\n\nfunction activePetSkillLevel',
    new_local_evolve,
    "replace local evolution logic",
)

replace_once(
    page,
    '    if (spend === 5 && !window.confirm("将合成并消耗 5 次变身机会，本次必定成功，但变身方向和强化特征仍然随机。继续吗？")) return;',
    '''    if (spend === 5) {
      const message = current.evolution_path && current.evolution_stage > 0
        ? "将消耗 5 张进化券改抽另一条路线。当前路线的进化层级与路线特征会清空，新路线固定从第 1 次进化开始；装备和已觉醒技能保留。继续吗？"
        : "将消耗 5 张进化券完成首次必定成功的进化，路线仍然随机。继续吗？";
      if (!window.confirm(message)) return;
    }''',
    "replace five-ticket confirmation",
)

replace_once(
    page,
    '        const result = await apiRequest<{ profile: PetProfile; success: boolean; spent: number; guaranteed: boolean; trait: string; critical?: boolean; skill?: PetSkill | null }>("/api/pet/evolve", { method: "POST", body: JSON.stringify({ spend }) });',
    '        const result = await apiRequest<{ profile: PetProfile; success: boolean; spent: number; guaranteed: boolean; trait: string; critical?: boolean; route_reset?: boolean; previous_path?: PetEvolutionPath; skill?: PetSkill | null }>("/api/pet/evolve", { method: "POST", body: JSON.stringify({ spend }) });',
    "extend evolve API result type",
)

old_success = '        if (result.success) wakePet(`${result.critical ? "暴击进化！" : "进化成功！"}获得「${result.trait}」${result.skill ? `，${result.skill.name} Lv.${result.skill.level}` : ""}`, next.evolution_path === "wonky" ? "worried" : "proud");'
new_success = '        if (result.success) wakePet(`${result.route_reset ? "换路线成功！从第 1 次进化重新开始。" : result.critical ? "暴击进化！" : "进化成功！"}获得「${result.trait}」${result.skill ? `，${result.skill.name} Lv.${result.skill.level}` : ""}`, next.evolution_path === "wonky" ? "worried" : "proud");'
text = page.read_text()
if text.count(old_success) != 2:
    raise RuntimeError(f"evolve success messages: expected 2 matches, found {text.count(old_success)}")
page.write_text(text.replace(old_success, new_success, 2))

replace_once(
    page,
    '<div className="pet-lottery-hero"><div className="pet-lottery-orbit"><PetCreatureVisual profile={profile} accessory={accessory} /><i>{profile.evolution_stage || "?"}</i></div><div><strong>{profile.evolution_path ? `${PET_EVOLUTION_PATHS[profile.evolution_path].tone}路线持续强化` : "9 条路线随机诞生"}</strong><p>首次成功决定主路线，之后不会洗掉原形态，只会继续叠加随机特征。每次成功有 12% 概率暴击并连续进化两次。</p><div className="pet-odds">',
    '<div className="pet-lottery-hero"><div className="pet-lottery-orbit"><PetCreatureVisual profile={profile} accessory={accessory} /><i>{profile.evolution_stage || "?"}</i></div><div><strong>{profile.evolution_path ? `${PET_EVOLUTION_PATHS[profile.evolution_path].tone}路线持续强化` : "9 条路线随机诞生"}</strong><p>{profile.evolution_path ? "单抽继续强化当前路线；使用 5 张进化券可改抽另一条路线，原路线层级与路线特征会清空，新路线从第 1 次进化开始。装备和技能保留。" : "首次成功决定主路线；之后单抽持续强化。获得路线后，也可以用 5 张进化券更换路线并从第 1 次进化重新开始。"}</p><div className="pet-odds">',
    "update evolution explanatory copy",
)

replace_once(
    page,
    '<button className="guaranteed" type="button" disabled={busy || profile.evolution_chances < 5} onClick={() => onEvolve(5)}><strong>五券聚变</strong><small>消耗 5 张 · 100% 成功</small></button>',
    '<button className="guaranteed" type="button" disabled={busy || profile.evolution_chances < 5} onClick={() => onEvolve(5)}><strong>{profile.evolution_path ? "五券换路线" : "五券首进化"}</strong><small>{profile.evolution_path ? "消耗 5 张 · 新路线从第 1 次开始" : "消耗 5 张 · 100% 成功"}</small></button>',
    "update five-ticket button",
)

replace_once(
    page,
    'event.type === "gift" ? event.sender : event.spent === 5 ? "五券聚变" : `单抽 ${event.success_rate ?? 10}%`',
    'event.type === "gift" ? event.sender : event.type === "reroute" ? "五券换路线" : event.spent === 5 ? "五券首进化" : `单抽 ${event.success_rate ?? 10}%`',
    "update evolution history label",
)

replace_once(
    page,
    '  const petProfileRef = useRef(petProfile);\n  const pettingBusyRef = useRef(false);',
    '  const petProfileRef = useRef(petProfile);\n  const petCustomizationSnapshot = useRef<Pick<PetProfile, "name" | "color" | "accessory"> | null>(null);\n  const pettingBusyRef = useRef(false);',
    "add appearance snapshot ref",
)

replace_once(
    page,
    '''      if (event.key === "Escape" && petSettingsOpen) {
        setPetSettingsOpen(false);
        return;
      }''',
    '''      if (event.key === "Escape" && petSettingsOpen) {
        const snapshot = petCustomizationSnapshot.current;
        if (snapshot) {
          const restored = { ...petProfileRef.current, color: snapshot.color, accessory: snapshot.accessory };
          petProfileRef.current = restored;
          setPetProfile(restored);
          setPetDraftName(snapshot.name);
          petCustomizationSnapshot.current = null;
        }
        setPetSettingsOpen(false);
        return;
      }''',
    "restore appearance preview on escape",
)

replace_once(
    page,
    '''  const togglePetStudio = () => {
    setPetSettingsOpen((current) => !current);
    if (!petSettingsOpen && serverUser?.role === "admin" && !serverUsers.length) {
      void apiRequest<ServerUser[]>("/api/users").then(setServerUsers).catch(() => undefined);
    }
  };''',
    '''  const togglePetStudio = () => {
    if (petSettingsOpen) {
      const snapshot = petCustomizationSnapshot.current;
      if (snapshot) {
        const restored = { ...petProfileRef.current, color: snapshot.color, accessory: snapshot.accessory };
        petProfileRef.current = restored;
        setPetProfile(restored);
        setPetDraftName(snapshot.name);
        petCustomizationSnapshot.current = null;
      }
      setPetSettingsOpen(false);
      return;
    }
    const current = petProfileRef.current;
    petCustomizationSnapshot.current = { name: current.name, color: current.color, accessory: current.accessory };
    setPetDraftName(current.name);
    setPetSettingsOpen(true);
    if (serverUser?.role === "admin" && !serverUsers.length) {
      void apiRequest<ServerUser[]>("/api/users").then(setServerUsers).catch(() => undefined);
    }
  };''',
    "make pet studio cancel-safe",
)

replace_once(
    page,
    '''      setPetSettingsOpen(false);
      wakePet(`以后就叫我「${name}」吧！`, "happy");''',
    '''      petCustomizationSnapshot.current = null;
      setPetSettingsOpen(false);
      wakePet(`以后就叫我「${name}」吧！`, "happy");''',
    "clear appearance snapshot after save",
)

replace_once(
    page,
    '<div className="pet-level-roadmap"><div className="pet-option-title"><span>等级路线 · 上限 50</span><small>Lv.5 后每级固定需要 {PET_STEADY_LEVEL_COST} EXP</small></div>',
    '<div className="pet-level-roadmap"><div className="pet-option-title"><span>称号里程碑 · 上限 50</span><small>外观按上方卡片标注等级解锁 · Lv.5 后每级 {PET_STEADY_LEVEL_COST} EXP</small></div>',
    "clarify level milestone semantics",
)

new_server_evolve = r'''@app.post("/api/pet/evolve")
def evolve_pet(body: PetEvolutionBody, user: CurrentUser, db: DB) -> dict[str, Any]:
    if body.spend not in {1, 5}:
        raise HTTPException(422, "进化只能使用 1 张或 5 张进化券")
    profile, progress, evolution, collection = get_or_create_pet(db, user.id)
    if evolution.available_chances < body.spend:
        raise HTTPException(422, "可用进化券不足")
    db.flush()
    evolution = db.scalar(
        select(PetEvolution)
        .where(PetEvolution.user_id == user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ) or evolution
    if evolution.available_chances < body.spend:
        raise HTTPException(409, "进化券刚刚发生变化，请刷新后重试")
    evolution.available_chances -= body.spend
    guaranteed = body.spend == 5
    route_reset = guaranteed and evolution.stage > 0 and evolution.path in PET_EVOLUTION_PATHS
    previous_path = evolution.path if route_reset else ""
    success_rate = pet_evolution_success_rate(collection)
    success = guaranteed or secrets.randbelow(100) < success_rate
    traits: list[str] = []
    critical = False
    awakened_skill: dict[str, Any] | None = None
    if success:
        if route_reset:
            reroll_pool = [candidate for candidate in PET_EVOLUTION_PATH_LOTTERY if candidate != previous_path]
            evolution.path = secrets.choice(reroll_pool)
            evolution.stage = 0
            evolution.traits = []
        elif evolution.stage == 0 or evolution.path not in PET_EVOLUTION_PATHS:
            evolution.path = secrets.choice(PET_EVOLUTION_PATH_LOTTERY)
        path = PET_EVOLUTION_PATHS[evolution.path]
        critical = False if route_reset else secrets.randbelow(100) < 12
        stage_gain = 1 if route_reset else 2 if critical else 1
        next_traits = list(evolution.traits or [])
        for stage_offset in range(stage_gain):
            next_stage = evolution.stage + stage_offset
            trait_pool = path["traits"][min(next_stage // 2, len(path["traits"]) - 1)]
            trait = secrets.choice(trait_pool)
            if next_stage >= len(path["traits"]) * 2:
                trait = f"{trait} · 星环{next_stage - len(path['traits']) * 2 + 1}"
            traits.append(trait)
            next_traits.append(trait)
        evolution.traits = next_traits[-24:]
        evolution.stage += stage_gain
        evolution.variant_seed = secrets.randbelow(8)
        collection.pity = 0
        awakened_skill = awaken_pet_skill(collection)
    else:
        collection.pity = min(20, collection.pity + 1)
        collection.updated_at = utcnow()
    event_trait = f"换路线 · {' / '.join(traits)}" if route_reset and success else " / ".join(traits)
    event = {
        "at": utcnow().isoformat(),
        **({"type": "reroute", "previous_path": previous_path, "route_reset": True} if route_reset else {}),
        "spent": body.spend,
        "guaranteed": guaranteed,
        "success": success,
        "stage": evolution.stage,
        "path": evolution.path,
        "trait": event_trait,
        "traits": traits,
        "critical": critical,
        "success_rate": 100 if guaranteed else success_rate,
        "pity_after": collection.pity,
        "skill": awakened_skill,
    }
    evolution.history = [event, *(evolution.history or [])][:50]
    evolution.updated_at = utcnow()
    db.commit()
    return {
        "profile": pet_dict(profile, progress, evolution, collection),
        "success": success,
        "spent": body.spend,
        "guaranteed": guaranteed,
        "route_reset": route_reset and success,
        "previous_path": previous_path,
        "trait": " / ".join(traits),
        "traits": traits,
        "critical": critical,
        "skill": awakened_skill,
    }


@app.put("/api/pet/equipment")'''
replace_regex(
    backend,
    r'@app\.post\("/api/pet/evolve"\)\ndef evolve_pet\(body: PetEvolutionBody, user: CurrentUser, db: DB\) -> dict\[str, Any\]:.*?\n\n\n@app\.put\("/api/pet/equipment"\)',
    new_server_evolve,
    "replace server evolution logic",
)

css_marker = "/* PET_STUDIO_APPEARANCE_FIXES_2026_09 */"
css_text = css.read_text()
if css_marker not in css_text:
    css_text += r'''

/* PET_STUDIO_APPEARANCE_FIXES_2026_09 */
.pet-appearance-panel { min-width: 0; overflow: hidden; }
.pet-appearance-panel .pet-option-title { min-width: 0; gap: 12px; }
.pet-appearance-panel .pet-option-title > small { max-width: 68%; text-align: right; line-height: 1.35; }
.pet-appearance-panel .pet-option-group button { min-width: 0; overflow: hidden; }
.pet-appearance-panel .pet-option-group button > span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pet-level-roadmap article { min-width: 0; }
.pet-level-roadmap article > div { min-width: 0; }
.pet-level-roadmap article strong,
.pet-level-roadmap article small,
.pet-level-roadmap article > span { overflow-wrap: anywhere; }
@media (max-width: 900px) {
  .pet-studio-backdrop { padding: 12px; }
  .pet-studio { width: 100%; max-height: calc(100vh - 24px); max-height: calc(100dvh - 24px); }
  .pet-studio-body { grid-template-columns: 1fr; max-height: calc(100vh - 166px); max-height: calc(100dvh - 166px); }
  .pet-studio-profile { border-right: 0; border-bottom: 1px solid var(--line-strong); }
  .pet-color-options > div:last-child { grid-template-columns: repeat(4,minmax(0,1fr)); }
  .pet-accessory-options > div:last-child { grid-template-columns: repeat(4,minmax(0,1fr)); }
}
@media (max-width: 620px) {
  .pet-studio-backdrop { padding: 6px; align-items: stretch; }
  .pet-studio { max-height: calc(100vh - 12px); max-height: calc(100dvh - 12px); box-shadow: 4px 4px 0 rgba(15,22,19,.35); }
  .pet-studio > header { min-height: 66px; padding: 11px 12px; gap: 10px; }
  .pet-studio > header h2 { font-size: 17px; }
  .pet-studio-body { max-height: calc(100vh - 128px); max-height: calc(100dvh - 128px); }
  .pet-studio-profile { padding: 16px 12px; }
  .pet-studio-editor { padding: 14px 12px; }
  .pet-studio-tabs { margin: -14px -12px 14px; padding: 8px; }
  .pet-color-options > div:last-child,
  .pet-accessory-options > div:last-child { grid-template-columns: repeat(2,minmax(0,1fr)); }
  .pet-level-roadmap > div:last-child { grid-template-columns: 1fr; }
  .pet-level-roadmap article { grid-template-columns: 42px minmax(0,1fr) auto; }
  .pet-studio > footer { padding: 9px 10px; align-items: stretch; flex-direction: column; }
  .pet-studio > footer > div { display: grid; grid-template-columns: 1fr 1fr; }
  .pet-studio > footer button { min-width: 0; }
}
'''
    css.write_text(css_text)

replace_once(
    readme,
    "- 宠物持续进化系统：每次升级积攒一张进化券；单抽具有动态保底，五券聚变必定成功；首次从 9 条路线随机诞生，之后沿原路线无限强化，并有暴击双重进化与随机技能觉醒",
    "- 宠物持续进化系统：每次升级积攒一张进化券；单抽具有动态保底并沿当前路线持续强化；已有路线后可消耗 5 张进化券改抽另一条路线，新路线从第 1 次进化重新开始；进化还会随机觉醒技能",
    "update README feature summary",
)

replace_once(
    readme,
    "宠物工作室分为“进化抽奖 / 装备 / 技能 / 外观与等级”四个区域。进化单抽基础成功率为 10%，每次连续失败都会提高保底，成功后重置；五券聚变始终成功，但路线特征、外观变体、技能和 12% 的暴击双重进化仍然随机。九条路线包含星辉、机甲、森灵、风暴、潮汐、火焰、云梦、像素，以及外观刻意不完美的“歪歪异变体”。首次成功决定路线，此后可不限三次地沿原路线持续强化。已有账号首次使用时，会按当前等级补发 `等级 - 1` 张进化券。",
    "宠物工作室分为“进化抽奖 / 装备 / 技能 / 外观与等级”四个区域。进化单抽基础成功率为 10%，每次连续失败都会提高保底，成功后重置；首次进化可用 5 张进化券保证成功。已有路线后再次使用 5 张进化券，会随机切换到一条不同路线，并清空旧路线的进化层级与路线特征，从新路线第 1 次进化重新开始；装备、已觉醒技能和历史记录保留。普通单抽成功时仍有 12% 概率暴击双重进化。九条路线包含星辉、机甲、森灵、风暴、潮汐、火焰、云梦、像素，以及外观刻意不完美的“歪歪异变体”。已有账号首次使用时，会按当前等级补发 `等级 - 1` 张进化券。",
    "update README detailed evolution rule",
)

page_text = page.read_text()
backend_text = backend.read_text()
assert '五券换路线' in page_text
assert 'route_reset: routeReset && success' in page_text
assert 'petCustomizationSnapshot' in page_text
assert '称号里程碑 · 上限 50' in page_text
assert '"route_reset": route_reset and success' in backend_text
assert 'evolution.stage = 0' in backend_text
assert css_marker in css.read_text()
print("Pet reroute and appearance fixes applied.")
