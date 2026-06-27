/**
 * Unified PageHeader — used on every sub-page (Files, Round Generator,
 * Schedule, Update Tool, Editor, etc.) to enforce a single back/home
 * navigation contract across the entire desktop app.
 *
 * Layout (always identical so muscle memory holds across pages):
 *   ┌──────────────────────────────────────────────────────────────┐
 *   │ [← Back]    [logo] Title             [→ Home]                 │
 *   │              Subtitle                                         │
 *   └──────────────────────────────────────────────────────────────┘
 *
 *   • Back arrow → browser history −1 (per-page previous step).
 *   • Home button → '/'   (always dashboard, NEVER a logout).
 *   • Position is locked: Back is top-LEFT, Home is top-RIGHT.
 *
 * Presenter views (Trivia / Bingo / Karaoke live shows) MUST NOT show
 * the Home button — a host could accidentally close the whole show
 * mid-event. Set `showHome={false}` on those views. Back is still
 * available so the host can step out manually if needed (or hide that
 * too via `showBack={false}` if the route should be a hard takeover).
 *
 * v32.0.0-alpha.18.
 */
import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { ArrowLeft, Home } from 'lucide-react';
import { Button } from './ui/button';

export default function PageHeader({
  title,
  subtitle,
  logoSrc = '/hat-logo.png',
  showBack = true,
  showHome = true,
  // Optional extra action slot (e.g. an "Upload .bighat" button on FilesTool).
  // Rendered at the far right, INSIDE the home button cluster.
  actions = null,
  // Variants for pages that have a light theme (Schedule page is white).
  variant = 'dark',
  // Optional custom back behaviour — defaults to navigate(-1). Use this
  // for pages where browser history isn't reliable (e.g. opened via a
  // deep link from a Tauri shortcut).
  onBack,
}) {
  const navigate = useNavigate();
  const location = useLocation();

  const goBack = () => {
    if (onBack) return onBack();
    // If history is empty (deep-linked into this page from a fresh tab),
    // fall back to the dashboard so users can never get stranded.
    if (window.history.length <= 1) {
      navigate('/');
    } else {
      navigate(-1);
    }
  };

  const onHome = location.pathname === '/';
  const isLight = variant === 'light';

  return (
    <header
      data-testid="page-header"
      className={`sticky top-0 z-40 ${isLight ? 'bg-white/80 backdrop-blur-md border-b border-gray-200' : 'glass'}`}
      style={!isLight ? { borderBottom: '1px solid rgba(251, 221, 104, 0.15)' } : undefined}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between min-h-16 py-3 gap-3">
          {/* LEFT — Back arrow (always top-left, identical position on every page). */}
          <div className="flex items-center gap-3 min-w-[88px]">
            {showBack && (
              <Button
                data-testid="page-header-back"
                variant={isLight ? 'outline' : 'ghost'}
                size="sm"
                onClick={goBack}
                aria-label="Back to previous page"
                title="Back"
                className={isLight ? '' : 'text-[#fbdd68] hover:bg-[rgba(251,221,104,0.12)]'}
              >
                <ArrowLeft className="w-4 h-4" />
                <span className="hidden sm:inline ml-2">Back</span>
              </Button>
            )}
          </div>

          {/* CENTER — title + subtitle + logo */}
          <div className="flex items-center gap-3 flex-1 justify-center text-center min-w-0">
            {logoSrc && (
              <img
                src={logoSrc}
                alt=""
                aria-hidden="true"
                className="h-9 w-9 object-contain flex-shrink-0 hidden sm:block"
              />
            )}
            <div className="min-w-0">
              {title && (
                <h1
                  data-testid="page-header-title"
                  className={`text-xl sm:text-2xl font-bold truncate ${isLight ? 'text-foreground' : ''}`}
                  style={!isLight ? { color: '#fbdd68' } : undefined}
                >
                  {title}
                </h1>
              )}
              {subtitle && (
                <p
                  data-testid="page-header-subtitle"
                  className={`text-xs sm:text-sm truncate ${isLight ? 'text-muted-foreground' : ''}`}
                  style={!isLight ? { color: '#8892b0' } : undefined}
                >
                  {subtitle}
                </p>
              )}
            </div>
          </div>

          {/* RIGHT — Home button (always top-right). Optional `actions` slot
              renders to its left so the Home anchor never moves. */}
          <div className="flex items-center gap-2 min-w-[88px] justify-end">
            {actions}
            {showHome && !onHome && (
              <Button
                data-testid="page-header-home"
                variant={isLight ? 'outline' : 'ghost'}
                size="sm"
                onClick={() => navigate('/')}
                aria-label="Return to dashboard"
                title="Home"
                className={isLight ? '' : 'text-[#fbdd68] hover:bg-[rgba(251,221,104,0.12)]'}
              >
                <Home className="w-4 h-4" />
                <span className="hidden sm:inline ml-2">Home</span>
              </Button>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}

export { PageHeader };
