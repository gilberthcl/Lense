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
