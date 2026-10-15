import { useEffect, useState } from 'react';
export interface Appearance { theme: 'light' | 'dark' | 'system'; reducedMotion: boolean; density: 'comfortable' | 'compact'; accent: 'lime' | 'sage' }
export const DEFAULT_APPEARANCE: Appearance = { theme: 'light', reducedMotion: false, density: 'comfortable', accent: 'lime' };
const KEY = 'analyst-os-appearance';
function read(): Appearance {
  try {
    const value = JSON.parse(localStorage.getItem(KEY) ?? '{}');
    return { theme: ['light', 'dark', 'system'].includes(value.theme) ? value.theme : 'light', reducedMotion: value.reducedMotion === true, density: value.density === 'compact' ? 'compact' : 'comfortable', accent: value.accent === 'sage' ? 'sage' : 'lime' };
  } catch { return DEFAULT_APPEARANCE; }
}
export function useAppearance() {
  const [appearance, setAppearance] = useState(read);
  const [storageError, setStorageError] = useState('');
  useEffect(() => {
    const sync = () => setAppearance(read());
    window.addEventListener('storage', sync); window.addEventListener('appearance-change', sync);
    return () => { window.removeEventListener('storage', sync); window.removeEventListener('appearance-change', sync); };
  }, []);
  function update(value: Appearance) {
    try { localStorage.setItem(KEY, JSON.stringify(value)); setStorageError(''); setAppearance(value); window.dispatchEvent(new Event('appearance-change')); }
    catch { setStorageError('Browser storage is unavailable. Preferences could not be saved.'); }
  }
  return { appearance, update, storageError };
}
export function useApplyAppearance() {
  const { appearance } = useAppearance();
  useEffect(() => {
    const query = window.matchMedia('(prefers-color-scheme: dark)');
    const apply = () => {
      document.documentElement.dataset.theme = appearance.theme === 'system' ? (query.matches ? 'dark' : 'light') : appearance.theme;
      document.documentElement.dataset.motion = appearance.reducedMotion ? 'reduce' : 'system';
      document.documentElement.dataset.density = appearance.density;
      document.documentElement.dataset.accent = appearance.accent;
    };
    apply(); query.addEventListener('change', apply);
    return () => query.removeEventListener('change', apply);
  }, [appearance]);
}
