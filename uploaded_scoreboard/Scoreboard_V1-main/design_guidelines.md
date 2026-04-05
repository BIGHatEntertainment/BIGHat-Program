{
  "brand": {
    "name": "BIG Hat Entertainment — Trivia Graphics Tool",
    "visual_personality": [
      "sports-broadcast energy (bold, high-contrast, LED-readable)",
      "Phoenix desert sunset atmosphere (silhouettes + warm sky)",
      "legally-safe ‘Phoenix basketball’ inspiration (no direct Suns marks)",
      "operator-first dashboard UI + zero-chrome render outputs"
    ],
    "success_actions": [
      "Pick mode (Leaderboard / Tournament)",
      "Connect to SharePoint JSON source",
      "Preview in exact aspect ratio",
      "Run animations",
      "Save/load presets",
      "Export PNG + WebM",
      "Open Live Render View (full screen)"
    ]
  },
  "design_tokens": {
    "note": "Implement as CSS custom properties in /frontend/src/index.css :root and .dark if needed. This app should default to a LIGHT operator dashboard, but render views can be ‘broadcast dark’.",
    "colors": {
      "core": {
        "ink": "#0B0A10",
        "paper": "#FBFAFF",
        "deepPurple": "#1D1160",
        "orange": "#E56020"
      },
      "broadcast_surface": {
        "broadcastBg": "#0A0718",
        "broadcastPanel": "rgba(16, 12, 34, 0.72)",
        "broadcastStroke": "rgba(255,255,255,0.14)",
        "broadcastText": "#F4F2FF",
        "broadcastMuted": "rgba(244,242,255,0.72)"
      },
      "desert_accents": {
        "sunsetPeach": "#FFB28A",
        "duskLavender": "#A48BFF",
        "sand": "#F4E6D4",
        "cactus": "#2AA775"
      },
      "semantic": {
        "primary": "#1D1160",
        "primaryFg": "#F6F2FF",
        "accent": "#E56020",
        "accentFg": "#1B0C06",
        "success": "#16A34A",
        "warning": "#F59E0B",
        "danger": "#DC2626",
        "info": "#2563EB",
        "focusRing": "rgba(229,96,32,0.55)"
      },
      "gradients": {
        "rule": "Gradients are REQUIRED for the bracket render theme. Keep gradient usage to section backgrounds and decorative overlays only; never on text-heavy reading areas in the operator dashboard.",
        "desertSunsetSky": "linear-gradient(180deg, #1D1160 0%, #3A1B7A 22%, #7A2C78 46%, #E56020 78%, #FFB28A 100%)",
        "desertSunsetSkySoft": "linear-gradient(180deg, #24146E 0%, #5A2A7C 45%, #E56020 100%)",
        "highlightSheen": "linear-gradient(90deg, rgba(255,255,255,0.00) 0%, rgba(255,255,255,0.22) 45%, rgba(255,255,255,0.00) 100%)"
      }
    },
    "typography": {
      "font_pairing": {
        "display": "Bebas Neue (sport headline, tall/condensed)",
        "ui": "IBM Plex Sans (operator UI + readable tables)",
        "numbers": "Azeret Mono (scores/seed numbers for stable alignment)"
      },
      "google_fonts_import": [
        "https://fonts.googleapis.com/css2?family=Bebas+Neue&family=IBM+Plex+Sans:wght@400;500;600;700&family=Azeret+Mono:wght@500;600&display=swap"
      ],
      "scale_tailwind": {
        "h1": "text-4xl sm:text-5xl lg:text-6xl font-semibold tracking-tight",
        "h2": "text-base md:text-lg text-muted-foreground",
        "body": "text-sm md:text-base",
        "small": "text-xs",
        "score": "font-mono tabular-nums"
      },
      "letter_spacing": {
        "display": "tracking-[0.08em] uppercase",
        "ui": "tracking-normal",
        "mono": "tracking-tight"
      }
    },
    "radius_shadow": {
      "radius": {
        "card": "16px",
        "control": "12px",
        "button": "12px",
        "pill": "999px"
      },
      "shadows": {
        "soft": "0 10px 30px rgba(10, 7, 24, 0.10)",
        "broadcastLift": "0 16px 60px rgba(0,0,0,0.45)",
        "innerGlow": "inset 0 1px 0 rgba(255,255,255,0.10)"
      },
      "strokes": {
        "hairline": "1px solid rgba(255,255,255,0.14)",
        "dashboardBorder": "1px solid rgba(29,17,96,0.14)"
      }
    },
    "spacing": {
      "layout": {
        "pagePadding": "px-4 sm:px-6 lg:px-10",
        "sectionGap": "gap-6 md:gap-8",
        "cardPadding": "p-4 sm:p-5"
      }
    }
  },
  "layout": {
    "operator_dashboard": {
      "structure": "Left rail (Mode/Data/Presets/Export) + main preview area + inspector drawer on mobile.",
      "grid": {
        "desktop": "grid grid-cols-12 gap-6",
        "rail": "col-span-12 lg:col-span-4 xl:col-span-3",
        "main": "col-span-12 lg:col-span-8 xl:col-span-9"
      },
      "preview": {
        "component": "AspectRatio (shadcn) wrapping a fixed-pixel stage",
        "stage_rule": "Render stage must be exact pixels: 1080x1920 (9:16) or 1920x1080 (16:9). Scale to fit using CSS transform: scale() in preview only. In Live Render View, no scaling—use exact canvas size.",
        "safe_margins": "Keep 64px safe padding inside render for titles/logos; keep bracket lines and text inside safe area to avoid cropping on venue projectors."
      }
    },
    "live_render_view": {
      "structure": "Full-screen, no dashboard chrome. Only the animated graphic output.",
      "rules": [
        "No scrollbars.",
        "No visible controls.",
        "Keyboard shortcut overlay can appear for operators (press ‘?’) but must be hidden by default.",
        "Add data-testid to the root render container for capture testing: data-testid=\"render-stage\"."
      ]
    },
    "render_modes": {
      "leaderboard": {
        "composition": "Top title bar + podium/top3 cards + scrolling list.",
        "top3": "Use a ‘spotlight’ treatment: angled glow + subtle shimmer sweep across the champion card.",
        "rest_list": "Use compact rows with rank pill + team name + total score; animate in staggered."
      },
      "tournament_bracket": {
        "composition": "Single elimination bracket with reseeding, 12-team example with top 4 byes.",
        "theme_locked": "Bracket must always use desertSunsetSky gradient + desert silhouettes.",
        "readability": "Use thick bracket lines, big seed numbers; prefer 2-line team names (wrap) with truncation fallback."
      }
    }
  },
  "components": {
    "component_path": {
      "shadcn_ui": [
        "/app/frontend/src/components/ui/button.jsx",
        "/app/frontend/src/components/ui/card.jsx",
        "/app/frontend/src/components/ui/tabs.jsx",
        "/app/frontend/src/components/ui/select.jsx",
        "/app/frontend/src/components/ui/switch.jsx",
        "/app/frontend/src/components/ui/slider.jsx",
        "/app/frontend/src/components/ui/input.jsx",
        "/app/frontend/src/components/ui/textarea.jsx",
        "/app/frontend/src/components/ui/scroll-area.jsx",
        "/app/frontend/src/components/ui/separator.jsx",
        "/app/frontend/src/components/ui/badge.jsx",
        "/app/frontend/src/components/ui/dialog.jsx",
        "/app/frontend/src/components/ui/sheet.jsx",
        "/app/frontend/src/components/ui/tooltip.jsx",
        "/app/frontend/src/components/ui/dropdown-menu.jsx",
        "/app/frontend/src/components/ui/table.jsx",
        "/app/frontend/src/components/ui/progress.jsx",
        "/app/frontend/src/components/ui/sonner.jsx"
      ],
      "render_helpers_to_create": [
        "Create /frontend/src/components/render/RenderStage.js (fixed-size stage with scaling helper for preview)",
        "Create /frontend/src/components/render/DesertBackdrop.js (gradient + silhouettes SVG layers)",
        "Create /frontend/src/components/render/LeaderboardRender.js",
        "Create /frontend/src/components/render/BracketRender.js",
        "Create /frontend/src/components/presets/PresetManager.js"
      ]
    },
    "control_panel_patterns": {
      "mode_switch": {
        "use": "Tabs",
        "testid": "mode-tabs"
      },
      "sharepoint_source": {
        "use": "Card + Input + Button + DropdownMenu",
        "fields": [
          { "name": "tenant", "testid": "sharepoint-tenant-input" },
          { "name": "site", "testid": "sharepoint-site-input" },
          { "name": "file", "testid": "sharepoint-file-picker" }
        ],
        "action": { "label": "Sync", "testid": "sharepoint-sync-button" }
      },
      "aspect_ratio": {
        "use": "Select or Segmented (Tabs)",
        "options": [
          { "label": "9:16 (Story)", "value": "portrait", "testid": "aspect-portrait-option" },
          { "label": "16:9 (Live)", "value": "landscape", "testid": "aspect-landscape-option" }
        ],
        "current": "data-testid=\"aspect-ratio-select\""
      },
      "export": {
        "use": "Button group",
        "buttons": [
          { "label": "Export PNG", "variant": "secondary", "testid": "export-png-button" },
          { "label": "Export WebM", "variant": "default", "testid": "export-webm-button" },
          { "label": "Open Live View", "variant": "outline", "testid": "open-live-view-button" }
        ]
      },
      "presets": {
        "use": "Dialog (save) + Sheet (browse/load)",
        "save": { "testid": "preset-save-button" },
        "load": { "testid": "preset-load-button" }
      }
    },
    "render_components": {
      "leaderboard": {
        "pods": [
          "TitleBar (location/date/round) — left aligned",
          "Top3PodiumCards (1st centered, 2nd left, 3rd right)",
          "ScrollingRankList (ranks 4+)"
        ],
        "top3_badges": {
          "1st": "Badge variant with orange fill + thin sheen overlay",
          "2nd": "Badge with lavender outline",
          "3rd": "Badge with sand outline"
        },
        "score_format": "Use Azeret Mono; always tabular-nums; align right."
      },
      "bracket": {
        "match_card": "Glass panel with strong border + inner glow. Display seed pill + team name + score.",
        "lines": "Use SVG path lines with stroke-width 4–6; animate stroke-dashoffset for reveal.",
        "champion": "Center trophy plate appears with scale+blur-in; then sheen sweep."
      }
    }
  },
  "motion": {
    "principles": [
      "Broadcast timing: fast entrance (200–350ms), slower settle (600–900ms).",
      "Stagger lists (60–90ms per row).",
      "Use transform + opacity for performance.",
      "Respect prefers-reduced-motion: disable shimmer/sweeps and reduce durations."
    ],
    "micro_interactions": {
      "buttons": {
        "hover": "bg shade shift + subtle glow shadow (no transform transition:all)",
        "press": "active:scale-[0.98] (add transition-transform ONLY on the button)",
        "focus": "ring-2 ring-[color:var(--focusRing)] ring-offset-2"
      },
      "toggle_switch": "Knob slide with 180ms ease-out; add tiny soundless tick via CSS (optional).",
      "cards": "Hover lifts 2px, shadow intensifies; use transition-shadow and transition-colors; if using transform, define transition-transform explicitly."
    },
    "render_animations_css": {
      "leaderboard_reveal": [
        "TitleBar slide-down + fade (280ms)",
        "Top3 pop-in (scale 0.96→1) with stagger 120ms",
        "Rows slide from left with stagger 70ms"
      ],
      "bracket_reveal": [
        "Background gradient slow drift (10–14s) very subtle",
        "Bracket lines draw-on using stroke-dasharray (900–1400ms per round)",
        "Match cards fade+lift (220ms) triggered per matchup",
        "Champion trophy: blur(8px)→0 + scale 0.94→1 (700ms)"
      ]
    }
  },
  "textures_and_backdrop": {
    "desert_backdrop": {
      "layers": [
        "Base gradient sky (desertSunsetSky)",
        "Subtle noise overlay (CSS) at 6–9% opacity",
        "Foreground silhouette SVG: mountains + cacti + skyline (single-color near-black)",
        "Optional: soft vignette to center attention"
      ],
      "silhouette_color": "rgba(8,6,18,0.86)",
      "noise_css_snippet": "background-image: url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='180' height='180'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.8' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='180' height='180' filter='url(%23n)' opacity='.35'/%3E%3C/svg%3E\"); mix-blend-mode: overlay; opacity: .08;"
    }
  },
  "images": {
    "image_urls": [
      {
        "category": "backdrop_photo_optional",
        "description": "If you want a faint photographic desert texture behind the vector silhouettes (keep VERY subtle, blur + opacity 0.10–0.18).",
        "urls": [
          "https://images.unsplash.com/photo-1577970136669-185bd3982878?crop=entropy&cs=srgb&fm=jpg&ixlib=rb-4.1.0&q=85",
          "https://images.pexels.com/photos/3967143/pexels-photo-3967143.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940"
        ]
      }
    ]
  },
  "libraries": {
    "recommended": [
      {
        "name": "framer-motion",
        "why": "Optional for operator UI transitions and staging; render animations should remain CSS-first for export consistency.",
        "install": "npm i framer-motion",
        "usage": "Use sparingly in dashboard; avoid in live render stage unless validated for export capture."
      },
      {
        "name": "html-to-image",
        "why": "PNG export of the render stage DOM.",
        "install": "npm i html-to-image",
        "usage": "Convert render-stage element to PNG (respect exact pixel size)."
      }
    ],
    "video_export_note": "WebM export typically uses MediaRecorder + canvas capture. If DOM-based, consider rendering stage to <canvas> via html2canvas/OffscreenCanvas, but validate performance. Keep guidelines flexible; main agent to choose implementation."
  },
  "implementation_notes_js": {
    "react_files": "Project uses .js (not .tsx). New components should be .js and use prop-types only if needed.",
    "data_testids": [
      "Every button/input/select/switch/tab must include data-testid.",
      "Render containers: data-testid=\"render-stage\", leaderboard: data-testid=\"leaderboard-render\", bracket: data-testid=\"bracket-render\".",
      "Rows: data-testid=\"leaderboard-row-{rank}\"; matchup cards: data-testid=\"match-card-r{round}-m{index}\".",
      "Export status text: data-testid=\"export-status\"."
    ],
    "tailwind_notes": [
      "Avoid `transition-all`. Use `transition-colors`, `transition-shadow`, `transition-opacity`, `transition-transform` intentionally.",
      "Use `tabular-nums` for scores.",
      "Prefer `backdrop-blur` only on broadcast panels; keep dashboard crisp for readability."
    ]
  },
  "accessibility": {
    "requirements": [
      "WCAG AA contrast in dashboard UI (operator).",
      "Focus rings always visible (ring + offset).",
      "Keyboard navigation for all controls.",
      "prefers-reduced-motion: reduce shimmer, drift, and long sweeps."
    ],
    "render_view_a11y": "Render view is primarily visual for broadcast; still add semantic headings and aria-labels for export controls in dashboard."
  },
  "instructions_to_main_agent": [
    "1) Replace CRA starter styles in /frontend/src/App.css; do NOT center the container. Use Tailwind + tokens in index.css.",
    "2) Implement a split layout dashboard with left rail controls and right live preview.",
    "3) Create a fixed-pixel RenderStage that can be scaled in preview but is exact size in Live Render View.",
    "4) Bracket theme is locked: desertSunsetSky gradient + silhouette layers + thick lines + glass match cards.",
    "5) Leaderboard: top 3 spotlight treatment + scrolling list for rest; ensure readable at distance.",
    "6) Add `data-testid` to every interactive element and key information.",
    "7) Keep gradients out of text-heavy operator cards; reserve them for render backgrounds only (<=20% viewport in dashboard)."
  ],
  "general_ui_ux_design_guidelines": "- You must **not** apply universal transition. Eg: `transition: all`. This results in breaking transforms. Always add transitions for specific interactive elements like button, input excluding transforms\n    - You must **not** center align the app container, ie do not add `.App { text-align: center; }` in the css file. This disrupts the human natural reading flow of text\n   - NEVER: use AI assistant Emoji characters like`🤖🧠💭💡🔮🎯📚🎭🎬🎪🎉🎊🎁🎀🎂🍰🎈🎨🎰💰💵💳🏦💎🪙💸🤑📊📈📉💹🔢🏆🥇 etc for icons. Always use **FontAwesome cdn** or **lucid-react** library already installed in the package.json\n\n **GRADIENT RESTRICTION RULE**\nNEVER use dark/saturated gradient combos (e.g., purple/pink) on any UI element.  Prohibited gradients: blue-500 to purple 600, purple 500 to pink-500, green-500 to blue-500, red to pink etc\nNEVER use dark gradients for logo, testimonial, footer etc\nNEVER let gradients cover more than 20% of the viewport.\nNEVER apply gradients to text-heavy content or reading areas.\nNEVER use gradients on small UI elements (<100px width).\nNEVER stack multiple gradient layers in the same viewport.\n\n**ENFORCEMENT RULE:**\n    • Id gradient area exceeds 20% of viewport OR affects readability, **THEN** use solid colors\n\n**How and where to use:**\n   • Section backgrounds (not content backgrounds)\n   • Hero section header content. Eg: dark to light to dark color\n   • Decorative overlays and accent elements only\n   • Hero section with 2-3 mild color\n   • Gradients creation can be done for any angle say horizontal, vertical or diagonal\n\n- For AI chat, voice application, **do not use purple color. Use color like light green, ocean blue, peach orange etc**\n\n</Font Guidelines>\n\n- Every interaction needs micro-animations - hover states, transitions, parallax effects, and entrance animations. Static = dead. \n   \n- Use 2-3x more spacing than feels comfortable. Cramped designs look cheap.\n\n- Subtle grain textures, noise overlays, custom cursors, selection states, and loading animations: separates good from extraordinary.\n   \n- Before generating UI, infer the visual style from the problem statement (palette, contrast, mood, motion) and immediately instantiate it by setting global design tokens (primary, secondary/accent, background, foreground, ring, state colors), rather than relying on any library defaults. Don't make the background dark as a default step, always understand problem first and define colors accordingly\n    Eg: - if it implies playful/energetic, choose a colorful scheme\n           - if it implies monochrome/minimal, choose a black–white/neutral scheme\n\n**Component Reuse:**\n\t- Prioritize using pre-existing components from src/components/ui when applicable\n\t- Create new components that match the style and conventions of existing components when needed\n\t- Examine existing components to understand the project's component patterns before creating new ones\n\n**IMPORTANT**: Do not use HTML based component like dropdown, calendar, toast etc. You **MUST** always use `/app/frontend/src/components/ui/ ` only as a primary components as these are modern and stylish component\n\n**Best Practices:**\n\t- Use Shadcn/UI as the primary component library for consistency and accessibility\n\t- Import path: ./components/[component-name]\n\n**Export Conventions:**\n\t- Components MUST use named exports (export const ComponentName = ...)\n\t- Pages MUST use default exports (export default function PageName() {...})\n\n**Toasts:**\n  - Use `sonner` for toasts\"\n  - Sonner component are located in `/app/src/components/ui/sonner.tsx`\n\nUse 2–4 color gradients, subtle textures/noise overlays, or CSS-based noise to avoid flat visuals."
}
