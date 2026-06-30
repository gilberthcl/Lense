/** @type {import('tailwindcss').Config} */

// The slate (structural) and indigo (accent) scales are backed by CSS variables
// so the whole app re-themes from index.css without touching component classes.
// Each var holds a space-separated "R G B" triplet (for <alpha-value> support).
const v = (name) => `rgb(var(${name}) / <alpha-value>)`;

const slate = Object.fromEntries(
  [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950].map((n) => [
    n,
    v(`--c-slate-${n}`),
  ]),
);
const indigo = Object.fromEntries(
  [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950].map((n) => [
    n,
    v(`--c-indigo-${n}`),
  ]),
);

// Semantic (status/badge) colors are ALSO var-backed so the light theme can
// invert them — otherwise `text-red-300` on `bg-red-950` stays light-on-light
// and is unreadable. Only the shades actually used in the app are mapped.
const SEMANTIC = {
  red: [200, 300, 400, 500, 700, 800, 900, 950],
  rose: [200, 300, 400, 800, 900, 950],
  amber: [200, 300, 400, 500, 800, 900, 950],
  orange: [200, 300, 800, 900, 950],
  emerald: [200, 300, 400, 500, 700, 800, 900, 950],
  teal: [300, 800, 950],
  cyan: [300, 800, 950],
  sky: [200, 900],
  blue: [300, 800, 950],
  purple: [300, 800, 950],
  violet: [300, 800, 950],
};
const semantic = Object.fromEntries(
  Object.entries(SEMANTIC).map(([name, shades]) => [
    name,
    Object.fromEntries(shades.map((n) => [n, v(`--c-${name}-${n}`)])),
  ]),
);

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: { slate, indigo, ...semantic },
      fontFamily: {
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Monaco",
          "Consolas",
          "Liberation Mono",
          "Courier New",
          "monospace",
        ],
      },
    },
  },
  plugins: [],
};
