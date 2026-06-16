/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        darkBg: "#0b0f17",
        darkCard: "#161b22",
        darkBorder: "#21262d",
        brandBlue: "#58a6ff",
        brandPurple: "#bc8cff",
        textMain: "#c9d1d9",
        textMuted: "#8b949e"
      }
    },
  },
  plugins: [],
}
