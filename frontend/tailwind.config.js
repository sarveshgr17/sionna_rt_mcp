/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        parchment: {
          DEFAULT: "#FBF9F5",
          sidebar: "#F6F4EE",
          surface: "#FFFFFF",
          subtle: "#F1EDE4",
          badge: "#EFECE4",
        },
        border: {
          light: "#EAE5DC",
          DEFAULT: "#E5E0D5",
          dark: "#D5CEBF",
        },
        rust: {
          light: "#FDF2EF",
          DEFAULT: "#C84B31",
          hover: "#B03D25",
          dark: "#99331D",
        },
        telemetry: {
          text: "#1E293B",
          muted: "#64748B",
          dim: "#94A3B8",
        },
        terminal: {
          bg: "#14181F",
          surface: "#1C222B",
          border: "#2A323F",
          text: "#E2E8F0",
        },
        signal: {
          green: "#16A34A",
          greenBg: "#E8F5E9",
          cyan: "#0284C7",
          cyanBg: "#E0F2FE",
          orange: "#EA580C",
          red: "#DC2626",
        }
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', '"IBM Plex Mono"', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', 'sans-serif'],
      },
      boxShadow: {
        'technical': '0 1px 2px 0 rgba(0, 0, 0, 0.03)',
        'technical-md': '0 2px 4px 0 rgba(0, 0, 0, 0.04), 0 1px 2px 0 rgba(0, 0, 0, 0.02)',
      },
      borderRadius: {
        'technical': '4px',
      }
    },
  },
  plugins: [],
}

