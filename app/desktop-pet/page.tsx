"use client";

import { useCallback, useEffect, useRef, useState, type CSSProperties, type FormEvent, type PointerEvent } from "react";
import { PetCreatureVisual, type PetVisualProfile } from "../pet-creature-visual";
import { PET_COLORS } from "../pet-visual-data";
import "./style.css";

type Choice = { id: string; name: string; rarity: string; effect_label?: string };
type PendingDrop = { token: string; choices: Choice[] };
type DesktopProfile = PetVisualProfile & {
  name: string;
  color: string;
  level: number;
  xp: number;
  next_level_xp: number;
  evolution_name: string;
  pending_drops: PendingDrop[];
};
type PetResult = { profile: DesktopProfile; awarded: boolean; amount: number; hourly_remaining: number; drop?: { name: string } | null };
type ApiError = Error & { status?: number };

declare global {
  interface Window {
    caseLensDesktop?: { moveBy(dx: number, dy: number): void; openStudio(section: "equipment" | "wardrobe"): void; close(): void };
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "same-origin",
    headers: { ...(init?.body ? { "Content-Type": "application/json" } : {}), ...init?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { detail?: string };
    throw Object.assign(new Error(body.detail || `请求失败：${response.status}`), { status: response.status });
  }
  return response.json() as Promise<T>;
}

export default function DesktopPet() {
  const [profile, setProfile] = useState<DesktopProfile | null>(null);
  const [loggedOut, setLoggedOut] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("轻轻摸摸小镜吧 ✦");
  const [busy, setBusy] = useState(false);
  const [showDrops, setShowDrops] = useState(false);
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const dragged = useRef(false);
  const busyRef = useRef(false);

  const refresh = useCallback(async () => {
    try {
      const next = await request<DesktopProfile>("/api/pet");
      setProfile(next);
      setLoggedOut(false);
    } catch (error) {
      if (error instanceof Error && (error as ApiError).status === 401) {
        setLoggedOut(true);
        setProfile(null);
      } else setMessage(error instanceof Error ? error.message : "暂时无法连接 CaseLens");
    }
  }, []);

  useEffect(() => {
    const initial = window.setTimeout(() => { void refresh(); }, 0);
    const timer = window.setInterval(() => { if (!document.hidden) void refresh(); }, 20_000);
    const onFocus = () => { void refresh(); };
    window.addEventListener("focus", onFocus);
    return () => { window.clearTimeout(initial); window.clearInterval(timer); window.removeEventListener("focus", onFocus); };
  }, [refresh]);

  const login = async (event: FormEvent) => {
    event.preventDefault();
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    try {
      await request("/api/auth/login", { method: "POST", body: JSON.stringify({ username, password }) });
      setPassword("");
      setMessage("欢迎回来，来摸摸小镜～");
      await refresh();
    } catch (error) { setMessage(error instanceof Error ? error.message : "登录失败"); }
    finally { busyRef.current = false; setBusy(false); }
  };

  const pet = async () => {
    if (!profile || busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    try {
      const result = await request<PetResult>("/api/pet/pet", { method: "POST", body: "{}" });
      setProfile(result.profile);
      setMessage(result.drop ? `摸出「${result.drop.name}」！选一件装备吧 ✦`
        : result.awarded ? `摸摸成功，经验 +${result.amount} ✦` : "本小时经验已满，还是可以摸摸我～");
      if (result.profile.pending_drops?.length) setShowDrops(true);
    } catch (error) { setMessage(error instanceof Error ? error.message : "摸摸失败，请重试"); }
    finally { busyRef.current = false; setBusy(false); }
  };

  const claim = async (pending: PendingDrop, choice: Choice) => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    try {
      const result = await request<{ profile: DesktopProfile }>("/api/pet/equipment/claim-drop", {
        method: "POST", body: JSON.stringify({ token: pending.token, item_id: choice.id }),
      });
      setProfile(result.profile);
      setShowDrops(Boolean(result.profile.pending_drops?.length));
      setMessage(`收下「${choice.name}」！`);
    } catch (error) { setMessage(error instanceof Error ? error.message : "领取失败，请重试"); }
    finally { busyRef.current = false; setBusy(false); }
  };

  const pointerDown = (event: PointerEvent<HTMLButtonElement>) => {
    if (event.button !== 0) return;
    dragged.current = false;
    drag.current = { x: event.screenX, y: event.screenY, moved: false };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const pointerMove = (event: PointerEvent<HTMLButtonElement>) => {
    const state = drag.current;
    if (!state) return;
    const dx = event.screenX - state.x;
    const dy = event.screenY - state.y;
    if (!state.moved && Math.hypot(dx, dy) < 5) return;
    state.moved = true;
    dragged.current = true;
    state.x = event.screenX;
    state.y = event.screenY;
    window.caseLensDesktop?.moveBy(dx, dy);
  };
  const pointerUp = (event: PointerEvent<HTMLButtonElement>) => {
    drag.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };
  const openStudio = (section: "equipment" | "wardrobe") => window.caseLensDesktop
    ? window.caseLensDesktop.openStudio(section)
    : window.open(`/?petStudio=${section}`, "_blank", "noopener,noreferrer");
  const color = PET_COLORS.find((item) => item.id === profile?.color)?.value ?? PET_COLORS[0].value;
  const pending = profile?.pending_drops?.[0];

  return <main className="desktop-pet-root" style={{ "--pet-color": color } as CSSProperties}>
    <header className="desktop-pet-handle" title="按住拖动小镜">
      <span><i /> CASELENS · DESKTOP PET</span>
      <button type="button" aria-label="关闭桌面宠物" title="关闭" onClick={() => window.caseLensDesktop?.close()}>×</button>
    </header>
    {loggedOut ? <form className="desktop-pet-login" onSubmit={(event) => void login(event)}>
      <strong>小镜在等你登录</strong>
      <small role="status">{message === "轻轻摸摸小镜吧 ✦" ? "使用 CaseLens 账号，衣柜和等级会同步。" : message}</small>
      <input autoComplete="username" aria-label="用户名" placeholder="用户名" value={username} onChange={(event) => setUsername(event.target.value)} required />
      <input autoComplete="current-password" type="password" aria-label="密码" placeholder="密码" value={password} onChange={(event) => setPassword(event.target.value)} required />
      <button disabled={busy} type="submit">进入宠物家园 ↗</button>
    </form> : <>
      <div className="desktop-pet-stage">
        {profile ? <button className="desktop-pet-touch" type="button" disabled={busy} aria-label={`摸摸${profile.name}，或拖动它移动位置`} onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp} onPointerCancel={() => { drag.current = null; dragged.current = true; }} onClick={() => { if (!dragged.current) void pet(); dragged.current = false; }}>
          <PetCreatureVisual profile={profile} accessory={profile.accessory !== "none" ? profile.accessory : undefined} />
        </button> : <span className="desktop-pet-loading">正在寻找小镜…</span>}
      </div>
      <div className="desktop-pet-speech" role="status" aria-live="polite">{message}</div>
      {profile ? <footer className="desktop-pet-actions">
        <span><b>{profile.name}</b> · Lv.{profile.level} <small>{profile.evolution_name}</small></span>
        <button type="button" onClick={() => void pet()} disabled={busy}>♡ 摸摸</button>
        <button type="button" onClick={() => pending ? setShowDrops(!showDrops) : openStudio("equipment")} aria-label={pending ? "查看待领取装备" : "打开装备仓库"}>{profile.pending_drops?.length ? `🎁 ${profile.pending_drops.length}` : "装备 ↗"}</button>
        <button type="button" onClick={() => openStudio("wardrobe")}>衣柜 ↗</button>
      </footer> : null}
      {showDrops && pending ? <section className="desktop-pet-drops" aria-label="三选一装备">
        <div><b>摸摸掉落 · 选一件</b><button type="button" onClick={() => setShowDrops(false)} aria-label="收起装备">×</button></div>
        {pending.choices.map((choice) => <button type="button" key={choice.id} disabled={busy} onClick={() => void claim(pending, choice)}><span>{choice.name}</span><small>{choice.effect_label || choice.rarity}</small></button>)}
      </section> : null}
    </>}
  </main>;
}
