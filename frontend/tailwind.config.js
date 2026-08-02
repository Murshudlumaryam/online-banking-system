/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#F7F6F2",
        ink: "#14171F",
        ledger: {
          50: "#EAF1F3",
          100: "#CFE0E5",
          200: "#A3C3CC",
          300: "#74A3B0",
          400: "#4C8494",
          500: "#2E6577",
          600: "#1B4A5C",
          700: "#123C4D",
          800: "#0D2E3C",
          900: "#08202A",
        },
        brass: {
          50: "#FBF4E8",
          100: "#F3E1C0",
          200: "#E6C68C",
          300: "#D6AB63",
          400: "#C6944A",
          500: "#B8935F",
          600: "#9C7940",
          700: "#7D5F31",
        },
        forest: { 500: "#2F6B4F", 600: "#245840" },
        brick: { 500: "#B33F32", 600: "#953427" },
        amber: { 500: "#C08A2E", 600: "#A3721F" },
        slate: {
          50: "#F5F6F7",
          100: "#E8EAEC",
          200: "#D3D7DB",
          300: "#AEB5BC",
          400: "#828C95",
          500: "#5F6B74",
          600: "#48535C",
          700: "#374149",
          800: "#242B31",
          900: "#161B1F",
        },
      },
      fontFamily: {
        display: ["'Source Serif 4'", "Georgia", "serif"],
        sans: ["'Inter'", "system-ui", "sans-serif"],
        mono: ["'IBM Plex Mono'", "ui-monospace", "monospace"],
      },
      boxShadow: {
        card: "0 1px 2px 0 rgb(20 23 31 / 0.06), 0 1px 0 0 rgb(20 23 31 / 0.04)",
      },
    },
  },
  plugins: [],
};
