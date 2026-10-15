import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import type { ReactNode } from 'react';
import { NavLink, Outlet, Link, useLocation, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard,
  Database,
  Server,
  Boxes,
  MessageSquare,
  BarChart3,
  Lightbulb,
  FileText,
  User,
  Settings,
  Menu,
  X,
  LogOut,
  Plus,
  PanelLeftClose,
  PanelLeftOpen,
  TrendingUp,
  Brain,
  Command,
  LayoutGrid,
  Activity,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { CommandPalette } from '../components/CommandPalette';
import { useCommandPalette } from '../hooks/useCommandPalette';
import { useApplyAppearance } from '../hooks/useAppearance';

// ---------------------------------------------------------------------------
// Storage key for sidebar preference persistence
// ---------------------------------------------------------------------------
const SIDEBAR_STORAGE_KEY = 'ai_data_analyst_sidebar_collapsed';

// ---------------------------------------------------------------------------
// Navigation structure (Single source of truth)
// ---------------------------------------------------------------------------

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  subItems?: { to: string; label: string }[];
}

interface NavGroup {
  label?: string;
  items: NavItem[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    label: 'WORKSPACE',
    items: [
      { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
    ],
  },
  {
    label: 'DATA MANAGEMENT',
    items: [
      { to: '/datasets', label: 'Datasets', icon: Database },
      { to: '/connections', label: 'Connections', icon: Server },
      { to: '/data-warehouse', label: 'Data Warehouse', icon: Boxes },
    ],
  },
  {
    label: 'ANALYTICS',
    items: [
      { to: '/analysis', label: 'AI Analysis', icon: MessageSquare },
      { to: '/eda', label: 'EDA Studio', icon: Activity },
      { to: '/visualizations', label: 'Visualizations', icon: BarChart3 },
      { to: '/insights', label: 'Insights', icon: Lightbulb },
      { to: '/forecasting', label: 'Forecasting', icon: TrendingUp },
    ],
  },
  {
    label: 'OUTPUT',
    items: [
      {
        to: '/reports',
        label: 'Reports',
        icon: FileText,
        subItems: [
          { to: '/reports/create', label: 'Create Report' },
        ],
      },
      { to: '/dashboard-studio', label: 'Dashboard Studio', icon: LayoutGrid },
    ],
  },
  {
    label: 'AI INTELLIGENCE',
    items: [
      { to: '/memory', label: 'AI Memory', icon: Brain },
    ],
  },
  {
    label: 'ACCOUNT',
    items: [
      { to: '/profile', label: 'Profile', icon: User },
      { to: '/settings', label: 'Settings', icon: Settings },
    ],
  },
];

// ---------------------------------------------------------------------------
// Page title map
// ---------------------------------------------------------------------------

const PAGE_TITLES: Record<string, string> = {
  '/dashboard': 'Dashboard',
  '/datasets': 'Datasets',
  '/datasets/upload': 'Upload Dataset',
  '/connections': 'Data Connections',
  '/data-warehouse': 'Data Warehouse',
  '/analysis': 'AI Analysis',
  '/visualizations': 'Visualizations',
  '/insights': 'Insights',
  '/insights/what-if': 'What-If Scenario Simulation',
  '/reports': 'Reports',
  '/reports/create': 'Create Report',
  '/forecasting': 'Forecasting Workbench',
  '/memory': 'AI Memory Explorer',
  '/dashboard-studio': 'Dashboard Studio',
  '/profile': 'Profile',
  '/settings': 'Settings',
};

function usePageTitle(): string {
  const { pathname } = useLocation();
  if (pathname.startsWith('/datasets/') && pathname !== '/datasets/upload') {
    return 'Dataset Details';
  }
  if (pathname.startsWith('/reports/') && pathname !== '/reports/create') {
    if (pathname.endsWith('/edit')) {
      return 'Report Builder';
    }
    return 'Generated Report';
  }
  return PAGE_TITLES[pathname] ?? 'AI Data Analyst';
}

// ---------------------------------------------------------------------------
// DockIcon — dock-style magnification on cursor proximity.
// Tooltip is a plain span rendered only when sidebar is collapsed;
// its visibility is controlled entirely by CSS (no JS state needed).
// ---------------------------------------------------------------------------

interface DockIconProps {
  children: ReactNode;
  isCollapsed: boolean;
  label: string;
}

function DockIcon({ children, isCollapsed, label }: DockIconProps) {
  return (
    <>
      <span className="ws-dock-icon" aria-hidden="true">{children}</span>
      {isCollapsed && <span className="ws-tooltip" role="tooltip">{label}</span>}
    </>
  );
}

function subscribeMobile(callback: () => void) {
  const query = window.matchMedia('(max-width: 768px)');
  query.addEventListener('change', callback);
  return () => query.removeEventListener('change', callback);
}
function mobileSnapshot() { return window.matchMedia('(max-width: 768px)').matches; }

// ---------------------------------------------------------------------------
// Sidebar Component
// ---------------------------------------------------------------------------

interface SidebarProps {
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  mobileOpen: boolean;
  isMobile: boolean;
  onMobileClose: () => void;
}

function Sidebar({ isCollapsed, onToggleCollapse, mobileOpen, isMobile, onMobileClose }: SidebarProps) {
  const { signOut } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const sidebarRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!mobileOpen) return;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const sidebar = sidebarRef.current;
    const focusable = () => (sidebar ? Array.from(sidebar.querySelectorAll<HTMLElement>('a[href], button:not([disabled])')) : []).filter(el => el.getClientRects().length > 0);
    focusable()[0]?.focus();
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); onMobileClose(); }
      if (event.key === 'Tab') {
        const items = focusable();
        const first = items[0];
        const last = items[items.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    };
    sidebar?.addEventListener('keydown', handleKey);
    return () => {
      sidebar?.removeEventListener('keydown', handleKey);
      if (previous?.isConnected) previous.focus();
    };
  }, [mobileOpen, onMobileClose]);

  // Show labels when expanded OR when mobile drawer is open.
  // This ensures the mobile drawer always shows full labels even if the
  // desktop sidebar was collapsed.
  const showLabels = !isCollapsed || mobileOpen;
  // Only apply dock magnification when truly collapsed (not in mobile drawer mode).
  const effectivelyCollapsed = isCollapsed && !mobileOpen;

  function handleSignOut() {
    signOut();
    navigate('/login');
  }

  return (
    <>
      {/* Mobile backdrop */}
      <div
        className={`ws-sidebar-overlay${mobileOpen ? ' ws-sidebar-overlay--visible' : ''}`}
        aria-hidden="true"
        onClick={onMobileClose}
      />

      <aside
        className={`ws-sidebar ${isCollapsed ? 'ws-sidebar--collapsed' : 'ws-sidebar--expanded'} ${mobileOpen ? 'ws-sidebar--open' : ''
          }`}
        aria-label="Main navigation"
        id="workspace-navigation"
        ref={sidebarRef}
        role={isMobile ? 'dialog' : undefined}
        aria-modal={mobileOpen || undefined}
        inert={isMobile && !mobileOpen}
      >
        {/* ── Brand header ── */}
        <div className="ws-sidebar-brand">
          <div className="ws-sidebar-brand-left">
            <div className="ws-sidebar-brand-dot" aria-hidden="true">
              <img src="/favicon.svg" width="28" height="28" alt="" />
            </div>
            {/* Brand text: CSS hides it when collapsed */}
            <span className="ws-sidebar-brand-text">AI Data Analyst OS</span>
          </div>

          {/* Desktop collapse/expand toggle — ONE control for both states */}
          <button
            type="button"
            className="ws-collapse-toggle"
            onClick={onToggleCollapse}
            aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            aria-expanded={!isCollapsed}
            title={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {isCollapsed ? (
              <PanelLeftOpen size={16} aria-hidden="true" />
            ) : (
              <PanelLeftClose size={16} aria-hidden="true" />
            )}
            {/* CSS tooltip for the toggle button when collapsed */}
            {isCollapsed && (
              <span className="ws-tooltip" role="tooltip">Expand sidebar</span>
            )}
          </button>

          {/* Mobile drawer close button */}
          <button
            type="button"
            className="ws-sidebar-mobile-close"
            onClick={onMobileClose}
            aria-label="Close navigation"
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        {/* ── New Analysis CTA ── */}
        <div className="ws-new-analysis-wrapper">
          <Link
            to="/analysis"
            className="ws-new-analysis"
            onClick={onMobileClose}
            aria-label="New Analysis"
          >
            <DockIcon isCollapsed={effectivelyCollapsed} label="New Analysis">
              <Plus size={20} strokeWidth={1.9} />
            </DockIcon>
            {/* Label rendered when sidebar is expanded OR mobile drawer is open */}
            {showLabels && (
              <span className="ws-new-analysis-label">New Analysis</span>
            )}
          </Link>
        </div>

        {/* ── Navigation groups — single source of truth: NAV_GROUPS ── */}
        <nav className="ws-sidebar-nav" aria-label="Main">
          {NAV_GROUPS.map((group, gi) => (
            <div key={gi} className="ws-nav-group">
              {gi > 0 && <div className="ws-nav-divider" aria-hidden="true" />}
              {/* Section label: not rendered when collapsed (unless mobile drawer is open) */}
              {group.label && showLabels && (
                <div className="ws-nav-section-label" aria-hidden="true">
                  {group.label}
                </div>
              )}
              {group.items.map((item) => {
                const { to, label, icon: Icon, subItems } = item;
                const isGroupActive = location.pathname.startsWith(to);
                return (
                  <div key={to} className="ws-nav-item-wrap">
                    <NavLink
                      to={to}
                      end={to === '/dashboard' || Boolean(subItems)}
                      className={({ isActive }) => `ws-nav-link${isActive || (Boolean(subItems) && isGroupActive) ? ' ws-nav-link--active' : ''}`}
                      aria-label={label}
                      onClick={onMobileClose}
                    >
                      <DockIcon
                        isCollapsed={effectivelyCollapsed}
                        label={label}
                      >
                        <Icon size={20} strokeWidth={1.9} />
                      </DockIcon>
                      {showLabels && (
                        <span className="ws-nav-label">{label}</span>
                      )}
                    </NavLink>
                    {showLabels && subItems && isGroupActive && (
                      <div className="ws-nav-subitems">
                        {subItems.map((sub) => (
                          <NavLink
                            key={sub.to}
                            to={sub.to}
                            end={sub.to === '/reports'}
                            className={({ isActive }) => `ws-nav-sublink${isActive ? ' ws-nav-sublink--active' : ''}`}
                            onClick={onMobileClose}
                          >
                            <span className="ws-nav-sublink-dot" aria-hidden="true" />
                            <span>{sub.label}</span>
                          </NavLink>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ))}
        </nav>

        {/* ── Footer: Sign out ── */}
        <div className="ws-sidebar-footer">
          <button
            type="button"
            className="ws-nav-link ws-signout-btn"
            onClick={handleSignOut}
            aria-label="Sign out"
          >
            <DockIcon isCollapsed={effectivelyCollapsed} label="Sign out">
              <LogOut size={20} strokeWidth={1.9} />
            </DockIcon>
            {showLabels && (
              <span className="ws-nav-label">Sign out</span>
            )}
          </button>
        </div>
      </aside>
    </>
  );
}

// ---------------------------------------------------------------------------
// AppLayout Component
// ---------------------------------------------------------------------------

export default function AppLayout() {
  useApplyAppearance();
  const { user } = useAuth();
  const initials = (user?.full_name || user?.email || 'Account').split(/\s+/).slice(0, 2).map(part => part[0]).join('').toUpperCase();
  const [isCollapsed, setIsCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem(SIDEBAR_STORAGE_KEY) === 'true';
    } catch {
      return false;
    }
  });
  const [mobileOpen, setMobileOpen] = useState(false);
  const isMobile = useSyncExternalStore(subscribeMobile, mobileSnapshot, () => false);
  const drawerOpen = mobileOpen && isMobile;
  const pageTitle = usePageTitle();
  const cmdPalette = useCommandPalette();

  const toggleCollapse = () => {
    setIsCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(SIDEBAR_STORAGE_KEY, String(next));
      } catch {
        // LocalStorage may be unavailable or disabled
      }
      return next;
    });
  };

  const closeMobile = useCallback(() => setMobileOpen(false), []);
  const toggleMobile = () => setMobileOpen((prev) => !prev);

  // Close mobile drawer on Escape key press
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && mobileOpen) {
        setMobileOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [mobileOpen]);

  return (
    <div className={`ws-shell ${isCollapsed ? 'ws-shell--collapsed' : 'ws-shell--expanded'}`}>
      <a href="#main-content" className="product-skip">Skip to main content</a>
      <div className="ws-app-frame">
        {/* Mobile hamburger button */}
        <button
          type="button"
          className="ws-sidebar-toggle"
          aria-label={mobileOpen ? 'Close navigation' : 'Open navigation'}
          aria-expanded={drawerOpen}
          aria-controls="workspace-navigation"
          onClick={toggleMobile}
        >
          {mobileOpen ? <X size={18} aria-hidden="true" /> : <Menu size={18} aria-hidden="true" />}
        </button>

        {/* Collapsible Sidebar */}
        <Sidebar
          isCollapsed={isCollapsed}
          onToggleCollapse={toggleCollapse}
          mobileOpen={drawerOpen}
          isMobile={isMobile}
          onMobileClose={closeMobile}
        />

        {/* Main Content Area */}
        <div className={`ws-main ${isCollapsed ? 'ws-main--collapsed' : 'ws-main--expanded'}`} inert={drawerOpen || cmdPalette.isOpen}>
          {/* Topbar */}
          <header className="ws-topbar">
            <nav className="ws-topbar-title" aria-label="Breadcrumb"><Link to="/dashboard">Workspace</Link><span aria-hidden="true"> / </span><span aria-current="page">{pageTitle}</span></nav>
            <div className="ws-topbar-actions">
              {/* Command Palette trigger */}
              <button
                type="button"
                className="ws-topbar-cmd"
                onClick={cmdPalette.open}
                aria-label="Open command palette (Ctrl+K)"
                title="Command palette (Ctrl+K)"
              >
                <Command size={14} aria-hidden="true" />
                <span className="ws-topbar-cmd-label">Search</span>
                <kbd className="ws-topbar-cmd-kbd">⌘K</kbd>
              </button>
              <Link
                to="/settings"
                className="ws-topbar-btn"
                aria-label="Settings"
              >
                <Settings size={16} aria-hidden="true" />
              </Link>
              <details className="account-disclosure" onKeyDown={event => { if (event.key === 'Escape') { event.currentTarget.open = false; event.currentTarget.querySelector('summary')?.focus(); } }} onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) event.currentTarget.open = false; }}>
                <summary className="ws-topbar-avatar" aria-label="Account options">{initials}</summary>
                <nav className="account-options" aria-label="Account" onClick={event => { if ((event.target as HTMLElement).closest('a')) event.currentTarget.closest('details')?.removeAttribute('open'); }}>
                  <span>{user?.full_name || 'Your account'}</span>
                  <Link to="/profile">View profile</Link>
                  <Link to="/settings">Account settings</Link>
                </nav>
              </details>
            </div>
          </header>

          {/* Routed page */}
          <main id="main-content" tabIndex={-1}>
            <Outlet />
          </main>
          <footer className="product-footer"><span>AI Data Analyst OS</span><nav aria-label="Legal"><Link to="/privacy">Privacy policy</Link><Link to="/terms">Terms</Link></nav></footer>
        </div>
      </div>

      {/* Global Command Palette */}
      <CommandPalette isOpen={cmdPalette.isOpen} onClose={cmdPalette.close} />
    </div>
  );
}
