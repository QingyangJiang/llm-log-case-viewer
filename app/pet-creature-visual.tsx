"use client";

import type { CSSProperties } from "react";
import { isIllustratedRoute, PetRouteArt } from "./pet-route-art";
import { PetFashionArt } from "./pet-fashion-art";
import { PetAccessoryArt, PetEquipmentArt } from "./pet-ornament-art";
import { PET_EVOLUTION_PATHS, PET_FASHION_CATALOG, type PetEvolutionPath, type PetFashionSlot, type PetRarity } from "./pet-visual-data";

type PetEquipmentSlot = "head" | "face" | "neck" | "back" | "tail";
type PetVisualEquipment = { id: string; slot: PetEquipmentSlot; rarity: PetRarity };
export type PetVisualProfile = {
  accessory: string;
  evolution_path: PetEvolutionPath;
  evolution_stage: number;
  evolution_variant: number;
  fashion: Partial<Record<PetFashionSlot, string>>;
  equipped: Partial<Record<PetEquipmentSlot, string>>;
  inventory: PetVisualEquipment[];
};

export function PetCreatureVisual({ profile, accessory, showEquipment = true, showFashion = true }: { profile: PetVisualProfile; accessory?: string; showEquipment?: boolean; showFashion?: boolean }) {
  const path = profile.evolution_path;
  const pathInfo = path ? PET_EVOLUTION_PATHS[path] : null;
  const illustrated = profile.evolution_stage >= 1 && isIllustratedRoute(path);
  const equippedItems = Object.values(profile.equipped).map((itemId) => profile.inventory.find((item) => item.id === itemId)).filter((item): item is PetVisualEquipment => Boolean(item));
  const fashionItems = showFashion ? (Object.entries(profile.fashion) as [PetFashionSlot, string][]).flatMap(([slot, itemId]) => {
    const item = PET_FASHION_CATALOG.find((candidate) => candidate.id === itemId && candidate.slot === slot);
    return item ? [item] : [];
  }) : [];
  return <span className={`pet-creature ${illustrated ? "pet-illustrated" : ""} evolution-${path || "base"} evolution-stage-${profile.evolution_stage} evolution-variant-${profile.evolution_variant}`} aria-hidden="true">
    {illustrated && isIllustratedRoute(path) ? <PetRouteArt path={path} stage={profile.evolution_stage} /> : <>
    {profile.evolution_stage >= 3 ? <span className="pet-evolution-aura" /> : null}
    {profile.evolution_stage >= 1 && pathInfo ? <><span className="pet-route-feature primary" /><span className="pet-route-feature secondary" /></> : null}
    {profile.evolution_stage >= 1 && pathInfo ? <span className="pet-evolution-mark">{pathInfo.motif}</span> : null}
    {profile.evolution_stage >= 2 ? <><span className="pet-evolution-wing left" /><span className="pet-evolution-wing right" /></> : null}
    {profile.evolution_stage >= 3 ? <span className="pet-evolution-crown" /> : null}
    <i className="pet-ear left" /><i className="pet-ear right" /><b className="pet-eye left" /><b className="pet-eye right" /><em /><span className="pet-tail" />
    </>}
    {fashionItems.map((item) => item.slot === "footwear" ? <span className={`pet-fashion pet-fashion-footwear fashion-theme-${item.theme}`} style={{ "--fashion-primary": item.primary, "--fashion-secondary": item.secondary } as CSSProperties} title={item.name} key={item.slot} /> : <PetFashionArt item={item} illustrated={illustrated} key={item.slot} />)}
    {accessory ? <span className={`pet-accessory accessory-${profile.accessory}`}><PetAccessoryArt id={profile.accessory} /></span> : null}
    {showEquipment ? equippedItems.map((item) => <span className={`pet-equipment pet-equipment-${item.slot} rarity-${item.rarity}`} key={item.slot}><PetEquipmentArt slot={item.slot} /></span>) : null}
  </span>;
}
