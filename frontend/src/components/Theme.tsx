import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

export type ThemeId = "midnight" | "graphite" | "daybreak";

export const THEMES: { id: ThemeId; label: string; swatch: string }[] = [
  { id: "midnight", label: "Midnight", swatch: "#6366f1" },
  { id: "graphite", label: "Graphite", swatch: "#14b8a6" },
  { id: "daybreak", label: "Daybreak", swatch: "#e2e8f0" },
];

// Authoritative theme variable maps. We apply these directly to <html> via JS
// (style.setProperty) so theming works regardless of any stylesheet build/cache
// state — the Tailwind slate/indigo scales read these vars.
type VarMap = Record<string, string>;
const THEME_VARS: Record<ThemeId, { scheme: "dark" | "light"; vars: VarMap }> = {
  midnight: {
    scheme: "dark",
    vars: {
      "--c-slate-50": "248 250 252", "--c-slate-100": "241 245 249",
      "--c-slate-200": "226 232 240", "--c-slate-300": "203 213 225",
      "--c-slate-400": "148 163 184", "--c-slate-500": "100 116 139",
      "--c-slate-600": "71 85 105", "--c-slate-700": "51 65 85",
      "--c-slate-800": "30 41 59", "--c-slate-900": "15 23 42",
      "--c-slate-950": "2 6 23",
      "--c-indigo-100": "224 231 255", "--c-indigo-200": "199 210 254",
      "--c-indigo-300": "165 180 252", "--c-indigo-400": "129 140 248",
      "--c-indigo-500": "99 102 241", "--c-indigo-600": "79 70 229",
      "--c-indigo-700": "67 56 202", "--scrollbar": "51 65 85",
    },
  },
  graphite: {
    scheme: "dark",
    vars: {
      "--c-slate-50": "250 250 249", "--c-slate-100": "245 245 244",
      "--c-slate-200": "231 229 228", "--c-slate-300": "214 211 209",
      "--c-slate-400": "168 162 158", "--c-slate-500": "120 113 108",
      "--c-slate-600": "87 83 78", "--c-slate-700": "68 64 60",
      "--c-slate-800": "41 37 36", "--c-slate-900": "28 25 23",
      "--c-slate-950": "12 10 9",
      "--c-indigo-100": "204 251 241", "--c-indigo-200": "153 246 228",
      "--c-indigo-300": "94 234 212", "--c-indigo-400": "45 212 191",
      "--c-indigo-500": "20 184 166", "--c-indigo-600": "13 148 136",
      "--c-indigo-700": "15 118 110", "--scrollbar": "68 64 60",
    },
  },
  daybreak: {
    scheme: "light",
    vars: {
      "--c-slate-50": "15 23 42", "--c-slate-100": "23 32 53",
      "--c-slate-200": "51 65 85", "--c-slate-300": "71 85 105",
      "--c-slate-400": "100 116 139", "--c-slate-500": "113 128 150",
      "--c-slate-600": "148 163 184", "--c-slate-700": "203 213 225",
      "--c-slate-800": "222 228 237", "--c-slate-900": "255 255 255",
      "--c-slate-950": "241 245 249",
      "--c-indigo-100": "224 231 255", "--c-indigo-200": "165 180 252",
      "--c-indigo-300": "79 70 229", "--c-indigo-400": "99 102 241",
      "--c-indigo-500": "99 102 241", "--c-indigo-600": "79 70 229",
      "--c-indigo-700": "67 56 202", "--scrollbar": "203 213 225",
    },
  },
};

const STORAGE_KEY = "lens-theme";

function applyTheme(id: ThemeId) {
  const root = document.documentElement;
  const theme = THEME_VARS[id];
  for (const [k, v] of Object.entries(theme.vars)) root.style.setProperty(k, v);
  root.style.colorScheme = theme.scheme;
  root.dataset.theme = id;
}

function readInitial(): ThemeId {
  const saved = localStorage.getItem(STORAGE_KEY) as ThemeId | null;
  return saved && THEMES.some((t) => t.id === saved) ? saved : "midnight";
}

const ThemeCtx = createContext<{ theme: ThemeId; setTheme: (t: ThemeId) => void }>({
  theme: "midnight",
  setTheme: () => {},
});

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemeId>(readInitial);

  useEffect(() => {
    applyTheme(theme);
    localStorage.setItem(STORAGE_KEY, theme);
  }, [theme]);

  return (
    <ThemeCtx.Provider value={{ theme, setTheme: setThemeState }}>
      {children}
    </ThemeCtx.Provider>
  );
}

export const useTheme = () => useContext(ThemeCtx);

/** Compact, text-free theme picker: one colored ball per theme. */
export function ThemeBalls() {
  const { theme, setTheme } = useTheme();
  return (
    <div className="flex items-center gap-2" role="radiogroup" aria-label="Theme">
      {THEMES.map((t) => {
        const active = t.id === theme;
        return (
          <button
            key={t.id}
            onClick={() => setTheme(t.id)}
            title={t.label}
            aria-label={`${t.label} theme`}
            aria-checked={active}
            role="radio"
            className={`h-5 w-5 rounded-full ring-1 ring-inset ring-black/30 transition-transform hover:scale-110 ${
              active
                ? "ring-2 ring-indigo-400 ring-offset-2 ring-offset-slate-950"
                : "opacity-70 hover:opacity-100"
            }`}
            style={{ backgroundColor: t.swatch }}
          />
        );
      })}
    </div>
  );
}
