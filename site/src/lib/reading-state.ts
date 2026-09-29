"use client";
import { useSyncExternalStore } from "react";
const KEY = "ai325-learning-v1";
const EVENT = "ai325-reading-change";
export interface ReadingState { saved: string[]; read: string[] }
const EMPTY: ReadingState = { saved: [], read: [] };
let previous: string | null = null;
let cached = EMPTY;
function snapshot(): ReadingState {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw === previous) return cached;
    previous = raw;
    const parsed = raw ? JSON.parse(raw) : EMPTY;
    const strings = (v: unknown): string[] => Array.isArray(v) ? [...new Set(v.filter((x): x is string => typeof x === "string"))] : [];
    cached = { saved: strings(parsed.saved), read: strings(parsed.read) };
  } catch { cached = EMPTY; }
  return cached;
}
function subscribe(listener: () => void) {
  window.addEventListener("storage", listener);
  window.addEventListener(EVENT, listener);
  return () => { window.removeEventListener("storage", listener); window.removeEventListener(EVENT, listener); };
}
export function toggleReading(id: string, field: keyof ReadingState) {
  const current = snapshot();
  const next = { ...current, [field]: current[field].includes(id) ? current[field].filter(value => value !== id) : [...current[field], id] };
  localStorage.setItem(KEY, JSON.stringify(next));
  window.dispatchEvent(new Event(EVENT));
}
export function useReadingState() { return useSyncExternalStore(subscribe, snapshot, () => EMPTY); }
