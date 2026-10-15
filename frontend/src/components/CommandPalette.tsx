/**
 * CommandPalette � Phase 23.1 Global Command Center
 *
 * Opens on Ctrl+K / Cmd+K. Provides sub-100ms fuzzy search across:
 *   - Navigation pages
 *   - Recent datasets
 *   - Quick actions (upload, new analysis, new report...)
 *   - Recent analyses / questions
 *
 * Keyboard nav: Arrow keys, Enter, Escape.
 * Zero external dependencies � pure React + CSS.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  LayoutDashboard,
  Database,
  MessageSquare,
  BarChart3,
  Lightbulb,
  FileText,
  Settings,
  User,
  Upload,
  Plus,
  Search,
  Server,
  Boxes,
  Sparkles,
  TrendingUp,
  Brain,
  Command,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type CommandCategory = 'navigation' | 'action' | 'dataset' | 'recent' | 'insight';

export interface CommandItem {
  id: string;
  label: string;
  description?: string;
  category: CommandCategory;
  icon: LucideIcon;
  path?: string;
  action?: () => void;
  shortcut?: string;
  keywords?: string[];
}

// ---------------------------------------------------------------------------
// Static command registry
// ---------------------------------------------------------------------------

const STATIC_COMMANDS: CommandItem[] = [
  { id: 'nav-dashboard',      label: 'Dashboard',             description: 'Go to command center',           category: 'navigation', icon: LayoutDashboard, path: '/dashboard',       keywords: ['home', 'overview', 'kpi'] },
  { id: 'nav-datasets',       label: 'Datasets',              description: 'Browse all datasets',            category: 'navigation', icon: Database,        path: '/datasets',        keywords: ['data', 'files', 'csv'] },
  { id: 'nav-analysis',       label: 'AI Analysis',           description: 'Chat with your data',            category: 'navigation', icon: MessageSquare,   path: '/analysis',        keywords: ['chat', 'ask', 'question', 'query'] },
  { id: 'nav-visualizations', label: 'Visualizations',        description: 'Charts and graphs',              category: 'navigation', icon: BarChart3,       path: '/visualizations',  keywords: ['chart', 'plot', 'graph'] },
  { id: 'nav-insights',       label: 'Insights Hub',          description: 'AI-generated business insights', category: 'navigation', icon: Lightbulb,       path: '/insights',        keywords: ['ai', 'recommendations', 'anomaly'] },
  { id: 'nav-reports',        label: 'Reports',               description: 'Executive reports and exports',  category: 'navigation', icon: FileText,        path: '/reports',         keywords: ['pdf', 'export', 'executive'] },
  { id: 'nav-forecasting',    label: 'Forecasting Workbench', description: 'Predict future trends',          category: 'navigation', icon: TrendingUp,      path: '/forecasting',     keywords: ['forecast', 'predict', 'prophet', 'xgboost'] },
  { id: 'nav-memory',         label: 'AI Memory Explorer',    description: 'View AI conversation history',   category: 'navigation', icon: Brain,           path: '/memory',          keywords: ['history', 'context', 'conversation'] },
  { id: 'nav-connections',    label: 'Connections',           description: 'Database connections',           category: 'navigation', icon: Server,          path: '/connections',     keywords: ['db', 'postgres', 'mysql', 'warehouse'] },
  { id: 'nav-warehouse',      label: 'Data Warehouse',        description: 'Data warehouse management',      category: 'navigation', icon: Boxes,           path: '/data-warehouse',  keywords: ['warehouse', 'tables', 'schema'] },
  { id: 'nav-profile',        label: 'Profile',               description: 'Your account profile',           category: 'navigation', icon: User,            path: '/profile',         keywords: ['account', 'user'] },
  { id: 'nav-settings',       label: 'Settings',              description: 'Platform configuration',         category: 'navigation', icon: Settings,        path: '/settings',        keywords: ['config', 'preferences', 'theme'] },
  { id: 'act-upload',         label: 'Upload Dataset',        description: 'Import a CSV or Excel file',     category: 'action',     icon: Upload,          path: '/datasets/upload', keywords: ['import', 'csv', 'excel', 'file'] },
  { id: 'act-new-analysis',   label: 'New Analysis',          description: 'Start a new AI conversation',   category: 'action',     icon: Plus,            path: '/analysis',        keywords: ['new', 'start', 'ask', 'question'] },
  { id: 'act-new-report',     label: 'Create Report',         description: 'Generate an executive report',  category: 'action',     icon: FileText,        path: '/reports/create',  keywords: ['report', 'pdf', 'create', 'generate'] },
];

// ---------------------------------------------------------------------------
// Fuzzy match scorer
// ---------------------------------------------------------------------------

function fuzzyScore(text: string, query: string): number {
  if (!query) return 1;
  const t = text.toLowerCase();
  const q = query.toLowerCase();
  if (t === q) return 100;
  if (t.startsWith(q)) return 90;
  if (t.includes(q)) return 70;
  let qi = 0;
  let score = 0;
  for (let i = 0; i < t.length && qi < q.length; i++) {
    if (t[i] === q[qi]) { score += 1; qi++; }
  }
  return qi === q.length ? 40 + score : 0;
}

function scoreCommand(cmd: CommandItem, query: string): number {
  if (!query.trim()) return 1;
  const scores = [
    fuzzyScore(cmd.label, query) * 2,
    fuzzyScore(cmd.description ?? '', query),
    ...(cmd.keywords ?? []).map((k: string) => fuzzyScore(k, query)),
  ];
  return Math.max(...scores);
}

// ---------------------------------------------------------------------------
// Category metadata
// ---------------------------------------------------------------------------

const CATEGORY_META: Record<CommandCategory, { label: string; order: number }> = {
  action:     { label: 'Quick Actions', order: 0 },
  navigation: { label: 'Navigate To',  order: 1 },
  recent:     { label: 'Recent',        order: 2 },
  dataset:    { label: 'Datasets',      order: 3 },
  insight:    { label: 'Insights',      order: 4 },
};

// ---------------------------------------------------------------------------
// CommandPalette component
// ---------------------------------------------------------------------------

interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
  dynamicItems?: CommandItem[];
}

export function CommandPalette({ isOpen, onClose, dynamicItems = [] }: CommandPaletteProps) {
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const allCommands = useMemo(() => [...STATIC_COMMANDS, ...dynamicItems], [dynamicItems]);

  const filtered = useMemo(() => {
    return allCommands
      .map(cmd => ({ cmd, score: scoreCommand(cmd, query) }))
      .filter(({ score }) => score > 0)
      .sort((a, b) => {
        if (b.score !== a.score) return b.score - a.score;
        return CATEGORY_META[a.cmd.category].order - CATEGORY_META[b.cmd.category].order;
      })
      .map(({ cmd }) => cmd)
      .slice(0, 24);
  }, [allCommands, query]);

  const grouped = useMemo(() => {
    const map = new Map<CommandCategory, CommandItem[]>();
    for (const cmd of filtered) {
      if (!map.has(cmd.category)) map.set(cmd.category, []);
      map.get(cmd.category)!.push(cmd);
    }
    return map;
  }, [filtered]);

  useEffect(() => {
    if (isOpen) {
      setQuery('');
      setActiveIndex(0);
      setTimeout(() => inputRef.current?.focus(), 10);
    }
  }, [isOpen]);

  useEffect(() => { setActiveIndex(0); }, [query]);

  useEffect(() => {
    const el = listRef.current?.querySelector(`[data-idx="${activeIndex}"]`) as HTMLElement | null;
    el?.scrollIntoView({ block: 'nearest' });
  }, [activeIndex]);

  const executeCommand = useCallback((cmd: CommandItem) => {
    onClose();
    if (cmd.action) {
      cmd.action();
    } else if (cmd.path) {
      navigate(cmd.path);
    }
  }, [navigate, onClose]);

  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActiveIndex(i => Math.min(i + 1, filtered.length - 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActiveIndex(i => Math.max(i - 1, 0));
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (filtered[activeIndex]) executeCommand(filtered[activeIndex]);
      } else if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [isOpen, filtered, activeIndex, executeCommand, onClose]);

  if (!isOpen) return null;

  let flatIdx = 0;
  const categoryEntries = [...grouped.entries()];

  return (
    <div className="cmd-overlay" onClick={onClose} role="dialog" aria-modal="true" aria-label="Command palette">
      <div className="cmd-panel" onClick={e => e.stopPropagation()}>
        <div className="cmd-header">
          <Search size={16} className="cmd-search-icon" aria-hidden="true" />
          <input
            ref={inputRef}
            className="cmd-input"
            type="text"
            placeholder="Search commands, datasets, pages..."
            value={query}
            onChange={e => setQuery(e.target.value)}
            aria-label="Command search"
            autoComplete="off"
            spellCheck={false}
          />
          <kbd className="cmd-esc-hint" aria-label="Press Escape to close">ESC</kbd>
        </div>

        <div className="cmd-results" ref={listRef} role="listbox" aria-label="Commands">
          {filtered.length === 0 && (
            <div className="cmd-empty">
              <Sparkles size={20} aria-hidden="true" />
              <span>No commands found for "<strong>{query}</strong>"</span>
            </div>
          )}

          {categoryEntries.map(([category, items]) => (
            <div key={category} className="cmd-group">
              <div className="cmd-group-label" aria-hidden="true">
                {CATEGORY_META[category].label}
              </div>
              {items.map(cmd => {
                const idx = flatIdx++;
                const isActive = idx === activeIndex;
                const Icon = cmd.icon;
                return (
                  <div
                    key={cmd.id}
                    className={`cmd-item${isActive ? ' cmd-item--active' : ''}`}
                    role="option"
                    aria-selected={isActive}
                    data-idx={idx}
                    onClick={() => executeCommand(cmd)}
                    onMouseEnter={() => setActiveIndex(idx)}
                  >
                    <span className={`cmd-item-icon cmd-item-icon--${cmd.category}`} aria-hidden="true">
                      <Icon size={15} />
                    </span>
                    <span className="cmd-item-body">
                      <span className="cmd-item-label">{cmd.label}</span>
                      {cmd.description && (
                        <span className="cmd-item-desc">{cmd.description}</span>
                      )}
                    </span>
                    {cmd.shortcut && (
                      <kbd className="cmd-item-shortcut">{cmd.shortcut}</kbd>
                    )}
                  </div>
                );
              })}
            </div>
          ))}
        </div>

        <div className="cmd-footer">
          <span className="cmd-footer-hint">
            <kbd>??</kbd> navigate <kbd>?</kbd> select <kbd>ESC</kbd> close
          </span>
          <span className="cmd-footer-brand">
            <Command size={11} aria-hidden="true" />
            Command Center
          </span>
        </div>
      </div>
    </div>
  );
}
