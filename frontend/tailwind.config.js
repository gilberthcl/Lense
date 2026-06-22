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
  [100, 200, 300, 400, 500, 600, 700].map((n) => [n, v(`--c-indigo-${n}`)]),
);

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: { slate, indigo },
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
