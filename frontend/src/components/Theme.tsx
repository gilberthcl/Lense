import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

export type ThemeId = "midnight" | "graphite" | "daybreak";

export const THEMES: { id: ThemeId; label: string; swatch: string }[] = [
  { id: "midnight", label: "Midnight", swatch: "#4a739e" },
  { id: "graphite", label: "Graphite", swatch: "#14b8a6" },
  { id: "daybreak", label: "Daybreak", swatch: "#e2e8f0" },
];

// Authoritative theme variable maps. We apply these directly to <html> via JS
// (style.setProperty) so theming works regardless of any stylesheet build/cache
// state — the Tailwind slate/indigo scales read these vars.
type VarMap = Record<string, string>;

// Semantic (status/badge) colors, also var-backed so the LIGHT theme can invert
// them — otherwise `text-red-300` on `bg-red-950` is light-on-light. Dark themes
// use Tailwind's palette; Daybreak uses each shade's mirror (n → 1000−n) so
// dark-fill/light-text combos flip to light-fill/dark-text and stay readable.
const SEMANTIC_DARK: VarMap = {
  "--c-red-200": "254 202 202", "--c-red-300": "252 165 165", "--c-red-400": "248 113 113",
  "--c-red-500": "239 68 68", "--c-red-700": "185 28 28", "--c-red-800": "153 27 27",
  "--c-red-900": "127 29 29", "--c-red-950": "69 10 10",
  "--c-rose-200": "254 205 211", "--c-rose-300": "253 164 175", "--c-rose-400": "251 113 133",
  "--c-rose-800": "159 18 57", "--c-rose-900": "136 19 55", "--c-rose-950": "76 5 25",
  "--c-amber-200": "253 230 138", "--c-amber-300": "252 211 77", "--c-amber-400": "251 191 36",
  "--c-amber-500": "245 158 11", "--c-amber-800": "146 64 14", "--c-amber-900": "120 53 15",
  "--c-amber-950": "69 26 3",
  "--c-orange-200": "254 215 170", "--c-orange-300": "253 186 116", "--c-orange-800": "154 52 18",
  "--c-orange-900": "124 45 18", "--c-orange-950": "67 20 7",
  "--c-emerald-200": "167 243 208", "--c-emerald-300": "110 231 183", "--c-emerald-400": "52 211 153",
  "--c-emerald-500": "16 185 129", "--c-emerald-700": "4 120 87", "--c-emerald-800": "6 95 70",
  "--c-emerald-900": "6 78 59", "--c-emerald-950": "2 44 34",
  "--c-teal-300": "94 234 212", "--c-teal-800": "17 94 89", "--c-teal-950": "4 47 46",
  "--c-cyan-300": "103 232 249", "--c-cyan-800": "21 94 117", "--c-cyan-950": "8 51 68",
  "--c-sky-200": "186 230 253", "--c-sky-900": "12 74 110",
  "--c-blue-300": "147 197 253", "--c-blue-800": "30 64 175", "--c-blue-950": "23 37 84",
  "--c-purple-300": "216 180 254", "--c-purple-800": "107 33 168", "--c-purple-950": "59 7 100",
  "--c-violet-300": "196 181 253", "--c-violet-800": "91 33 182", "--c-violet-950": "46 16 101",
};
const SEMANTIC_LIGHT: VarMap = {
  "--c-red-200": "153 27 27", "--c-red-300": "185 28 28", "--c-red-400": "220 38 38",
  "--c-red-500": "239 68 68", "--c-red-700": "252 165 165", "--c-red-800": "254 202 202",
  "--c-red-900": "254 226 226", "--c-red-950": "254 242 242",
  "--c-rose-200": "159 18 57", "--c-rose-300": "190 18 60", "--c-rose-400": "225 29 72",
  "--c-rose-800": "254 205 211", "--c-rose-900": "255 228 230", "--c-rose-950": "255 241 242",
  "--c-amber-200": "146 64 14", "--c-amber-300": "180 83 9", "--c-amber-400": "217 119 6",
  "--c-amber-500": "245 158 11", "--c-amber-800": "253 230 138", "--c-amber-900": "254 243 199",
  "--c-amber-950": "255 251 235",
  "--c-orange-200": "154 52 18", "--c-orange-300": "194 65 12", "--c-orange-800": "254 215 170",
  "--c-orange-900": "255 237 213", "--c-orange-950": "255 247 237",
  "--c-emerald-200": "6 95 70", "--c-emerald-300": "4 120 87", "--c-emerald-400": "5 150 105",
  "--c-emerald-500": "16 185 129", "--c-emerald-700": "110 231 183", "--c-emerald-800": "167 243 208",
  "--c-emerald-900": "209 250 229", "--c-emerald-950": "236 253 245",
  "--c-teal-300": "15 118 110", "--c-teal-800": "153 246 228", "--c-teal-950": "240 253 250",
  "--c-cyan-300": "14 116 144", "--c-cyan-800": "165 243 252", "--c-cyan-950": "236 254 255",
  "--c-sky-200": "7 89 133", "--c-sky-900": "224 242 254",
  "--c-blue-300": "29 78 216", "--c-blue-800": "191 219 254", "--c-blue-950": "239 246 255",
  "--c-purple-300": "126 34 206", "--c-purple-800": "233 213 255", "--c-purple-950": "250 245 255",
  "--c-violet-300": "109 40 217", "--c-violet-800": "221 214 254", "--c-violet-950": "245 243 255",
};
const THEME_VARS: Record<ThemeId, { scheme: "dark" | "light"; vars: VarMap }> = {
  // Gunmetal neutrals + steel-blue accent (deeper, cooler, less violet).
  midnight: {
    scheme: "dark",
    vars: {
      "--c-slate-50": "245 247 250", "--c-slate-100": "236 240 245",
      "--c-slate-200": "213 220 230", "--c-slate-300": "182 192 206",
      "--c-slate-400": "136 149 168", "--c-slate-500": "95 108 128",
      "--c-slate-600": "66 79 99", "--c-slate-700": "45 56 74",
      "--c-slate-800": "25 33 47", "--c-slate-900": "13 19 30",
      "--c-slate-950": "6 10 18",
      "--c-indigo-50": "235 242 248",
      "--c-indigo-100": "219 229 240", "--c-indigo-200": "181 201 223",
      "--c-indigo-300": "140 170 203", "--c-indigo-400": "99 138 180",
      "--c-indigo-500": "74 115 158", "--c-indigo-600": "57 92 132",
      "--c-indigo-700": "46 74 107", "--c-indigo-800": "36 58 85",
      "--c-indigo-900": "28 46 68", "--c-indigo-950": "17 30 46",
      "--scrollbar": "45 56 74",
      ...SEMANTIC_DARK,
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
      "--c-indigo-50": "240 253 250",
      "--c-indigo-100": "204 251 241", "--c-indigo-200": "153 246 228",
      "--c-indigo-300": "94 234 212", "--c-indigo-400": "45 212 191",
      "--c-indigo-500": "20 184 166", "--c-indigo-600": "13 148 136",
      "--c-indigo-700": "15 118 110", "--c-indigo-800": "17 94 89",
      "--c-indigo-900": "19 78 74", "--c-indigo-950": "4 47 46",
      "--scrollbar": "68 64 60",
      ...SEMANTIC_DARK,
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
      // Steel-blue accent (matches Midnight's), mapped for light surfaces.
      "--c-indigo-50": "235 242 248",
      "--c-indigo-100": "219 229 240", "--c-indigo-200": "181 201 223",
      "--c-indigo-300": "46 74 107", "--c-indigo-400": "57 92 132",
      "--c-indigo-500": "74 115 158", "--c-indigo-600": "57 92 132",
      "--c-indigo-700": "46 74 107",
      // Dark steel fills (badges) → light tints on light surfaces.
      "--c-indigo-800": "181 201 223", "--c-indigo-900": "213 226 238",
      "--c-indigo-950": "235 242 248",
      "--scrollbar": "203 213 225",
      ...SEMANTIC_LIGHT,
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
