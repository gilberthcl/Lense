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
  { id: "daybreak", label: "Daybreak", swatch: "#f1f5f9" },
];

const STORAGE_KEY = "lens-theme";

function readInitial(): ThemeId {
  const saved = localStorage.getItem(STORAGE_KEY) as ThemeId | null;
  return saved && THEMES.some((t) => t.id === saved) ? saved : "midnight";
}

const ThemeCtx = createContext<{
  theme: ThemeId;
  setTheme: (t: ThemeId) => void;
}>({ theme: "midnight", setTheme: () => {} });

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemeId>(readInitial);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem(STORAGE_KEY, theme);
  }, [theme]);

  return (
    <ThemeCtx.Provider value={{ theme, setTheme: setThemeState }}>
      {children}
    </ThemeCtx.Provider>
  );
}

export const useTheme = () => useContext(ThemeCtx);

export function ThemeSwitcher() {
  const { theme, setTheme } = useTheme();
  return (
    <div className="px-3 py-2">
      <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-600">
        Theme
      </p>
      <div className="flex gap-1.5">
        {THEMES.map((t) => {
          const active = t.id === theme;
          return (
            <button
              key={t.id}
              onClick={() => setTheme(t.id)}
              title={t.label}
              aria-label={`${t.label} theme`}
              className={`flex h-7 flex-1 items-center justify-center gap-1.5 rounded-md border text-[11px] transition-colors ${
                active
                  ? "border-indigo-500/50 bg-indigo-500/10 text-indigo-200"
                  : "border-slate-700 text-slate-400 hover:bg-slate-800/60"
              }`}
            >
              <span
                className="h-3 w-3 rounded-full ring-1 ring-inset ring-black/20"
                style={{ backgroundColor: t.swatch }}
              />
              {t.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
