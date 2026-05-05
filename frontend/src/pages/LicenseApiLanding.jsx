import React, { useEffect, useState } from 'react';
import { ArrowRight, Cloud, ShoppingBag } from 'lucide-react';

const STOREFRONT_URL = 'https://bighat.live';
const REDIRECT_SECONDS = 8;

/**
 * Public landing page shown when the React frontend is served from an `api.*`
 * hostname (e.g. `api.bighat.live`). It exists so curious visitors don't see
 * the desktop app's internal Master Admin login. Auto-redirects to the
 * Squarespace storefront after a short delay.
 *
 * The desktop app on a customer's PC ALWAYS connects to api.bighat.live
 * via direct `/api/*` calls, never by visiting `/`, so this page is only
 * ever seen by humans who landed here by mistake.
 */
export default function LicenseApiLanding() {
  const [seconds, setSeconds] = useState(REDIRECT_SECONDS);

  useEffect(() => {
    const interval = setInterval(() => {
      setSeconds((s) => (s > 0 ? s - 1 : 0));
    }, 1000);
    const timeout = setTimeout(() => {
      window.location.href = STOREFRONT_URL;
    }, REDIRECT_SECONDS * 1000);
    return () => {
      clearInterval(interval);
      clearTimeout(timeout);
    };
  }, []);

  return (
    <div
      className="min-h-screen flex items-center justify-center px-6"
      style={{ backgroundColor: '#000e2a' }}
      data-testid="license-api-landing"
    >
      <div className="absolute top-1/4 left-1/4 w-96 h-96 rounded-full opacity-20 animate-pulse-glow"
           style={{ background: 'radial-gradient(circle, #fbdd68 0%, transparent 70%)' }} />
      <div className="absolute bottom-1/4 right-1/4 w-80 h-80 rounded-full opacity-15 animate-pulse-glow"
           style={{ background: 'radial-gradient(circle, #5973F7 0%, transparent 70%)',
                    animationDelay: '2s' }} />

      <div className="relative z-10 w-full max-w-lg text-center animate-slide-up">
        <img src="/hat-logo.png" alt="BIG Hat" className="w-20 h-20 mx-auto mb-4 object-contain" />
        <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-[#5973F7]/15 border border-[#5973F7]/30 mb-5">
          <Cloud className="w-4 h-4 text-[#5973F7]" />
          <span className="text-xs font-bold uppercase tracking-wider text-[#5973F7]">
            License API Server
          </span>
        </div>

        <h1
          className="text-3xl sm:text-4xl font-bold mb-3 font-['Lemonada']"
          style={{ color: '#fbdd68' }}
          data-testid="license-api-landing-title"
        >
          You're in the wrong place
        </h1>

        <p className="text-base text-white/80 mb-6 leading-relaxed">
          This URL is the BIG Hat Entertainment <strong>license API</strong> —
          it's used by your installed desktop app to verify your purchase. It
          isn't where you download or use the program.
        </p>

        <div className="glass-card rounded-xl p-5 mb-6 text-left text-sm space-y-2">
          <p className="text-white/90 font-semibold mb-2">Looking for…</p>
          <p className="text-[#8892b0]">
            <span className="text-[#fbdd68] font-semibold">📥 The downloadable program?</span>
            <br />
            Visit <a href={STOREFRONT_URL} className="text-[#5973F7] underline">bighat.live</a> to
            purchase BIG Hat Entertainment ($49.99).
          </p>
          <p className="text-[#8892b0] pt-2 border-t border-white/5">
            <span className="text-[#fbdd68] font-semibold">🎟️ Already bought it?</span>
            <br />
            Open the app you installed on your computer (search "BIG Hat" in
            your Start Menu / Applications) and paste your license key into
            the Setup Wizard.
          </p>
        </div>

        <a
          href={STOREFRONT_URL}
          data-testid="license-api-landing-store-btn"
          className="inline-flex items-center gap-2 px-6 py-3 rounded-full bg-[#fbdd68] text-[#000e2a] font-bold text-base hover:bg-[#fbdd68]/90 transition-colors shadow-lg"
        >
          <ShoppingBag className="w-5 h-5" />
          Go to bighat.live
          <ArrowRight className="w-5 h-5" />
        </a>

        <p className="mt-5 text-xs text-white/40">
          Auto-redirecting in {seconds}s…
        </p>
      </div>
    </div>
  );
}
