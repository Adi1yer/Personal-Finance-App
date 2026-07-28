/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: "#0f1419",
          raised: "#161d26",
          overlay: "#1c2530",
          border: "#2a3544",
        },
        accent: {
          DEFAULT: "#3b82f6",
          muted: "#2563eb",
          soft: "rgba(59, 130, 246, 0.12)",
        },
        positive: "#22c55e",
        negative: "#ef4444",
        muted: "#94a3b8",
      },
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          "SF Pro Text",
          "Segoe UI",
          "sans-serif",
        ],
      },
      boxShadow: {
        card: "0 1px 3px rgba(0,0,0,0.35), 0 4px 12px rgba(0,0,0,0.25)",
      },
    },
  },
  plugins: [],
};
