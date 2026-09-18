"use client";

import { ChangeEvent, CSSProperties, DragEvent, ReactNode, UIEvent, useCallback, useDeferredValue, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { BADCASE_AUTO_SCORE_THRESHOLD, shouldAutoMarkBadcase } from "./annotation-rules";
import { MarkdownContent } from "./markdown-content";
import { cleanApiBaseUrl, modelApiEndpoint, modelApiRequest } from "./model-api";
import type { ApiProtocol, ModelApiMessage } from "./model-api";

type JsonObject = Record<string, unknown>;
type CandidateOutput = { id: string; model: string; label?: string; reasoning?: unknown; response?: unknown; metadata?: JsonObject };
type AnnotationDimension = { key: string; label: string; description?: string; min?: number; max?: number; required?: boolean };
type CaseAnnotation = {
  annotation_id: string;
  annotator: { id: string; name: string };
  candidate_id: string;
  scores: Record<string, number>;
  badcase: boolean;
  badcase_tags?: string[];
  note?: string;
  status: "draft" | "submitted";
  revision?: number;
  sync_state?: "pending" | "error";
  created_at: string;
  updated_at: string;
};
type AnnotationConfig = { dimensions?: AnnotationDimension[]; badcase_tags?: string[]; model_order?: string[]; blind_mode?: boolean; lock_submitted?: boolean };
type LogCase = JsonObject & {
  schema_version?: string;
  id?: string | number;
  model?: string;
  messages?: JsonObject[];
  tools?: JsonObject[];
  candidates?: CandidateOutput[];
  refer_info?: JsonObject;
  annotation_config?: AnnotationConfig;
  annotations?: CaseAnnotation[];
  __server_case_id?: number;
  __assigned_user_ids?: string[];
  __line?: number;
};
type ServerUser = { id: string; username: string; display_name: string; role: "admin" | "annotator"; active: boolean };
type ServerProject = { id: number; name: string; archived?: boolean; annotation_config?: AnnotationConfig; case_count: number; my_submitted_count: number; created_at: string };
type ProjectMemberOption = ServerUser & { member: boolean };
type AssignmentMember = { id: string; username: string; display_name: string; assigned_count: number; submitted_count: number; draft_count: number; external_ids: string[] };
type AssignmentOverview = { total_cases: number; assigned_cases: number; unassigned_cases: number; submitted_annotations: number; draft_annotations: number; members: AssignmentMember[]; settings: AnnotationConfig };
type SaveState = "idle" | "dirty" | "saving" | "saved" | "error";

type Protocol = "openai" | "anthropic" | "unknown";
type ViewTab = "conversation" | "candidates" | "tools" | "raw" | "ai";
const VIEW_TABS: ViewTab[] = ["conversation", "candidates", "tools", "raw", "ai"];
const MESSAGE_ROLE_LABELS: Record<string, string> = { system: "SYSTEM", user: "USER", assistant: "ASSISTANT", tool: "TOOL", developer: "DEVELOPER" };
type AiTask = "summary" | "translate" | "bilingual" | "custom";
type AiTarget =
  | { kind: "case" }
  | { kind: "message"; index: number }
  | { kind: "batch" }
  | { kind: "tool-definition"; index: number }
  | { kind: "message-tool"; messageIndex: number; itemIndex: number; source: "content" | "tool_call" };
type ProviderMode = "local" | "external";
type PetMood = "idle" | "happy" | "proud" | "curious" | "worried";
type PetColor = "lime" | "aqua" | "peach" | "lavender" | "sky" | "coral" | "gold" | "midnight" | "rose" | "jade" | "violet" | "sunset" | "ice" | "fuchsia" | "emerald" | "azure" | "ruby" | "pearl" | "aurora" | "cosmos";
type PetAccessory = "none" | "leaf" | "bow" | "glasses" | "star" | "headphones" | "cap" | "crown" | "halo" | "medal";
type PetFashionSlot = "headwear" | "outfit" | "outerwear" | "footwear" | "handheld";
type PetFashionItem = { id: string; name: string; slot: PetFashionSlot; slot_name: string; symbol: string; theme: string; theme_name: string; level: number; rarity: PetRarity; primary: string; secondary: string };
type PetEvolutionPath = "" | "starlight" | "guardian" | "forest" | "storm" | "ocean" | "ember" | "cloud" | "pixel" | "wonky";
type PetRarity = "common" | "uncommon" | "rare" | "epic" | "legendary";
type PetEquipmentSlot = "head" | "face" | "neck" | "back" | "tail";
type PetEquipmentSort = "theme_slot" | "slot_theme" | "power" | "level" | "rarity" | "count";
type PetAutoEquipMode = "combat" | "evolution" | "annotation" | "pet" | "badcase" | "rarity";
type PetEquipmentEffectKey = "all_drop_bonus" | "pet_drop_bonus" | "annotation_drop_bonus" | "badcase_drop_bonus" | "evolution_bonus" | "rarity_boost";
type PetEquipmentAffix = { id: string; key: PetEquipmentEffectKey; label: string; value: number; critical: boolean };
type PetEquipment = { id: string; name: string; slot: PetEquipmentSlot; slot_name: string; symbol: string; rarity: PetRarity; theme: string; count: number; level: number; power: number; effect_key: Exclude<PetEquipmentEffectKey, "rarity_boost">; effect_label: string; effect_value: number; affixes: PetEquipmentAffix[]; synthesis_failures: number; synthesis_success_rate: number };
type PetEquipmentStats = { total_power: number; all_drop_bonus: number; pet_drop_bonus: number; annotation_drop_bonus: number; badcase_drop_bonus: number; evolution_bonus: number; rarity_boost: number };
type PetEquipmentSetTier = { pieces: number; key: PetEquipmentEffectKey; value: number; label: string };
type PetEquipmentSet = { theme: string; name: string; description: string; pieces: number; bonuses: string[]; tiers: (Omit<PetEquipmentSetTier, "key" | "value"> & { active: boolean })[] };
type PetWardrobePreset = { id: string; name: string; color: PetColor; accessory: PetAccessory; fashion: Partial<Record<PetFashionSlot, string>>; fashion_saved?: boolean; equipped: Partial<Record<PetEquipmentSlot, string>>; created_at: string };
type PetSkill = { id: string; name: string; icon: string; description: string; level: number; active: boolean };
type PetDropReason = "pet" | "annotation" | "badcase" | "battle" | "wheel";
type PetDropEvent = PetEquipment & { reason: PetDropReason; duplicate: boolean; identified_affix?: PetEquipmentAffix; affix_added?: boolean; at: string };
type PetDropChoice = Pick<PetEquipment, "id" | "name" | "slot" | "slot_name" | "symbol" | "rarity" | "theme" | "effect_label" | "effect_value"> & { is_new: boolean; owned_count: number; owned_level?: number | null; owned_affix_count: number; count_after_claim: number; materials_to_synthesize: number; theme_owned_count: number; theme_equipped_count: number; theme_pieces_if_equipped: number; next_set_target?: number | null; next_set_bonus?: string | null; equipped_same_slot?: { id: string; name: string; rarity: PetRarity; level: number; power: number } | null; hidden_affix?: PetEquipmentAffix };
type PetPendingDrop = { token: string; reason: PetDropReason; at: string; choices: PetDropChoice[] };
type PetDropReveal = { drop: PetDropEvent; identified_affix: PetEquipmentAffix; affix_added: boolean };
type PetEvolutionEvent = { at: string; type?: "gift" | "reroute" | "targeted_reroute"; spent: number; guaranteed?: boolean; success: boolean; stage: number; path: PetEvolutionPath; trait: string; traits?: string[]; critical?: boolean; success_rate?: number; pity_after?: number; amount?: number; sender?: string; previous_path?: PetEvolutionPath; target_path?: PetEvolutionPath; route_reset?: boolean; wheel_compensation?: number; skill?: PetSkill | null };
type PetWheelReward = { id: string; label: string; short_label: string; icon: string; probability: number; tone: string };
type PetWheelEvent = { reward_id: string; label: string; short_label: string; icon: string; tone: string; detail: string; at: string };
type PetWheelSpinResult = { profile: PetProfile; reward: PetWheelEvent; reward_index: number; pending_drop?: PetPendingDrop | null };
type PetProfile = {
  name: string;
  color: PetColor;
  accessory: PetAccessory;
  xp: number;
  level: number;
  title?: string;
  current_level_xp?: number;
  next_level_xp?: number;
  earned_event_keys?: string[];
  evolution_chances: number;
  evolution_credited_level: number;
  evolution_stage: number;
  evolution_path: PetEvolutionPath;
  evolution_name?: string;
  evolution_quality?: string;
  evolution_variant: number;
  evolution_traits: string[];
  evolution_history: PetEvolutionEvent[];
  equipment_catalog_size: number;
  equipment_parts: number;
  inventory: PetEquipment[];
  equipped: Partial<Record<PetEquipmentSlot, string>>;
  equipment_stats: PetEquipmentStats;
  equipment_sets: PetEquipmentSet[];
  fashion: Partial<Record<PetFashionSlot, string>>;
  fashion_catalog_size: number;
  wardrobe_presets: PetWardrobePreset[];
  skills: PetSkill[];
  active_skills: string[];
  drop_history: PetDropEvent[];
  pending_drops: PetPendingDrop[];
  wheel_chances: number;
  wheel_history: PetWheelEvent[];
  wheel_rewards: PetWheelReward[];
  targeted_evolution_target: PetEvolutionPath;
  targeted_evolution_failures: number;
  targeted_evolution_blessings: number;
  targeted_evolution_success_rate: number;
  total_drops: number;
  evolution_pity: number;
  evolution_success_rate: number;
};
type PetHomeEquipment = Pick<PetEquipment, "id" | "name" | "slot" | "slot_name" | "symbol" | "rarity" | "theme" | "level" | "power">;
type PetHomeSkill = Pick<PetSkill, "id" | "name" | "icon" | "level">;
type PetHomeSet = Pick<PetEquipmentSet, "theme" | "name" | "pieces" | "bonuses">;
type PetHomeResident = {
  user_id: string;
  owner_name: string;
  pet_name: string;
  color: PetColor;
  accessory: PetAccessory;
  fashion: Partial<Record<PetFashionSlot, string>>;
  level: number;
  title: string;
  evolution_stage: number;
  evolution_path: PetEvolutionPath;
  evolution_name: string;
  evolution_variant: number;
  evolution_traits: string[];
  battle_power: number;
  power_breakdown: { base: number; level: number; evolution: number; equipment: number; skills: number; sets: number };
  equipped_items: PetHomeEquipment[];
  active_skills: PetHomeSkill[];
  active_sets: PetHomeSet[];
  rank?: number;
};
type PetBattleHistory = {
  id: string;
  at: string;
  day: string;
  outcome: "win" | "loss" | "draw";
  my_power: number;
  opponent_power: number;
  power_delta: number;
  reward: boolean;
  opponent: PetHomeResident;
};
type PetHomeData = {
  me: PetHomeResident;
  residents: PetHomeResident[];
  resident_count: number;
  battle_available: boolean;
  battled_today: boolean;
  battle_day: string;
  next_battle_at: string;
  recent_battles: PetBattleHistory[];
};
type PetBattleResult = {
  outcome: "win" | "loss" | "draw";
  won: boolean;
  lucky_reward?: boolean;
  my_power: number;
  opponent_power: number;
  opponent: PetHomeResident;
  reward_pending?: PetPendingDrop | null;
  profile: PetProfile;
  home: PetHomeData;
};
type PetForgeResult = { profile: PetProfile; item: PetEquipment; level_up: boolean; identified_affix: PetEquipmentAffix; affix_added: boolean };
type AiResult = {
  resultId: string;
  content: string;
  error?: string;
  prompt?: string;
  task: AiTask;
  target: string;
  caseId: string;
  caseIndex: number;
  messageIndex?: number;
  anchorId?: string;
  model: string;
  provider: ProviderMode;
  sourceChars: number;
  sourceTokens: number;
  calls: number;
  chunks: number;
  sampled: boolean;
  createdAt: string;
};

type AiSource = { item: LogCase; caseIndex: number; caseId: string; target: string; source: string; messageIndex?: number; anchorId?: string };
type AiPlan = { sourceTokens: number; calls: number; chunks: number; blocked: boolean; clipped: boolean };
type AiContentOptions = { includeSystem: boolean; includeThinking: boolean; includeTools: boolean };
type MetricDimension = { key: string; label: string; min?: number; max?: number };
type MetricCaseType = "all" | "agent" | "non_agent";
type MetricTier = { count: number; pct: number };
type MetricModel = {
  model: string;
  n: number;
  avg: number;
  median: number;
  std: number;
  tiers: { tier_1: MetricTier; tier_2: MetricTier; tier_3: MetricTier };
  badcase_rate: number;
  manual_badcase_rate: number;
  score_hist: number[];
  out_of_range_count: number;
};
type MetricScope = {
  id: string;
  label: string;
  annotator_id?: string | null;
  candidate_complete_case_count: number;
  attempted_case_count: number;
  complete_case_count: number;
  dropped_case_count: number;
  complete_rate: number;
  models: MetricModel[];
};
type MetricsData = { dimension: MetricDimension; dimensions: MetricDimension[]; models: string[]; case_type: MetricCaseType; case_type_counts: Record<MetricCaseType, number>; total_case_count: number; scopes: MetricScope[] };
type ChatMessage = ModelApiMessage & { id: string };
type JudgeConfig = {
  configured: boolean;
  has_api_key: boolean;
  version: number;
  protocol: "anthropic" | "openai";
  base_url: string;
  model_name: string;
  stage1_temperature: number;
  stage2_temperature: number;
  stage3_temperature: number;
  stage1_max_tokens: number;
  stage2_max_tokens: number;
  stage3_max_tokens: number;
  concurrency: number;
  sample_count: number;
  adaptive_sampling: boolean;
  input_limit: number;
  seed: number;
  timeout_seconds: number;
  max_retries: number;
  rubric: string;
  decomposer_prompt: string;
  detector_prompt: string;
  verifier_prompt: string;
  lifecycle_status?: "draft" | "test" | "published" | "archived";
  version_note?: string;
  parent_version?: number | null;
  source_self_check_id?: number | null;
  shared?: boolean;
  is_default?: boolean;
  created_by_id?: number;
  active?: boolean;
  created_at?: string;
  created_by?: string;
};
type JudgePromptVersion = JudgeConfig & { version: number; active: boolean; lifecycle_status: "draft" | "test" | "published" | "archived"; created_at: string; created_by: string; shared: boolean; is_default: boolean; created_by_id: number };
type JudgeCandidateResult = { id: number; candidate_id: string; status: string; stage2?: JsonObject | null; stage3?: JsonObject | null; stage2_raw?: string; stage3_raw?: string; error?: string; started_at?: string | null; completed_at?: string | null };
type JudgeSelfCheckResult = { id: number; result: JsonObject; raw_output: string; triggered_by: string; created_at: string };
type JudgeCaseResult = { case_id: number; external_id: string; status: string; stage1?: JsonObject | null; stage1_raw?: string; error?: string; config_version: number; candidates: Record<string, JudgeCandidateResult>; self_check?: JudgeSelfCheckResult | null };
type JudgeHistoryRun = { id: number; status: string; stage1?: JsonObject | null; stage1_raw?: string; error?: string; config_version: number; model_name: string; current_case_content: boolean; triggered_by: string; created_at: string; completed_at?: string | null; candidates: (JudgeCandidateResult & { candidate_hash: string; current_content: boolean })[] };
type JudgeStatusData = {
  config: JudgeConfig;
  summary: { not_started: number; queued: number; running: number; succeeded: number; failed: number; stale: number; cancelled: number };
  running: boolean;
  cases: Record<string, JudgeCaseResult>;
};
const JUDGE_LOCAL_RELAY_URL = "http://127.0.0.1:19001/v1";

const DEFAULT_DIMENSIONS: AnnotationDimension[] = [
  { key: "correctness", label: "正确性", description: "事实、结论与工具使用是否正确", min: 1, max: 5, required: true },
  { key: "relevance", label: "相关性", description: "是否直接解决用户任务", min: 1, max: 5, required: true },
  { key: "completeness", label: "完整性", description: "关键信息与步骤是否完整", min: 1, max: 5, required: true },
  { key: "clarity", label: "表达质量", description: "结构、语言和可读性", min: 1, max: 5, required: true },
];
const DEFAULT_BADCASE_TAGS = ["事实错误", "未遵循指令", "工具调用错误", "推理问题", "遗漏关键信息", "表达问题", "安全风险", "其他"];
const EMPTY_JUDGE_CONFIG: JudgeConfig = {
  configured: false,
  has_api_key: false,
  version: 0,
  protocol: "anthropic",
  base_url: JUDGE_LOCAL_RELAY_URL,
  model_name: "DeepSeek-V4-F