import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#123B5D", clinic: "#247BA0", health: "#19A78C", mint: "#DDF7F2", paper: "#F5F8FA",
        muted: "#4A6378", sim: { DEFAULT: "#9A5800", soft: "#FFF3DC" }, alert: { DEFAULT: "#A3261C", soft: "#FDEEEC" },
      },
      fontFamily: { sans: ['"Archivo Variable"', "Archivo", "system-ui", "sans-serif"] },
      maxWidth: { page: "72rem" },
    },
  },
  plugins: [],
} satisfies Config;
