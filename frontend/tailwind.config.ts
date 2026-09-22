import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['IBM Plex Sans', 'Inter', '-apple-system', 'sans-serif'],
        mono: ['IBM Plex Mono', 'SF Mono', 'Menlo', 'monospace'],
      },
      colors: {
        bg: 'rgb(var(--bg) / <alpha-value>)',
        bg2: 'rgb(var(--bg2) / <alpha-value>)',
        surface: 'rgb(var(--surface) / <alpha-value>)',
        surface2: 'rgb(var(--surface2) / <alpha-value>)',
        surface3: 'rgb(var(--surface3) / <alpha-value>)',
        border: 'rgb(var(--border) / <alpha-value>)',
        border2: 'rgb(var(--border2) / <alpha-value>)',
        border3: 'rgb(var(--border3) / <alpha-value>)',
        text: 'rgb(var(--text) / <alpha-value>)',
        text2: 'rgb(var(--text2) / <alpha-value>)',
        text3: 'rgb(var(--text3) / <alpha-value>)',
        text4: 'rgb(var(--text4) / <alpha-value>)',
        red: {
          DEFAULT: 'rgb(var(--red) / <alpha-value>)',
          dim: 'rgb(var(--red-dim) / <alpha-value>)',
          bg: 'rgb(var(--red-bg) / <alpha-value>)',
        },
        amber: {
          DEFAULT: 'rgb(var(--amber) / <alpha-value>)',
          dim: 'rgb(var(--amber-dim) / <alpha-value>)',
          bg: 'rgb(var(--amber-bg) / <alpha-value>)',
        },
        green: {
          DEFAULT: 'rgb(var(--green) / <alpha-value>)',
          dim: 'rgb(var(--green-dim) / <alpha-value>)',
          bg: 'rgb(var(--green-bg) / <alpha-value>)',
        },
        blue: {
          DEFAULT: 'rgb(var(--blue) / <alpha-value>)',
          bg: 'rgb(var(--blue-bg) / <alpha-value>)',
        },
        teal: {
          DEFAULT: 'rgb(var(--teal) / <alpha-value>)',
          dim: 'rgb(var(--teal-dim) / <alpha-value>)',
          bg: 'rgb(var(--teal-bg) / <alpha-value>)',
        },
        purple: 'rgb(var(--purple) / <alpha-value>)',
      },
      borderRadius: {
        token: '6px',
        'token-lg': '10px',
      },
      keyframes: {
        pulse: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.45' },
        },
        fadeIn: {
          from: { opacity: '0', transform: 'translateY(2px)' },
          to: { opacity: '1', transform: 'none' },
        },
        tickerSlide: {
          from: { opacity: '0', transform: 'translateY(-8px)' },
          to: { opacity: '1', transform: 'none' },
        },
        floatIn: {
          from: { opacity: '0', transform: 'translateX(20px)' },
          to: { opacity: '1', transform: 'none' },
        },
        bounce3: {
          '0%, 80%, 100%': { transform: 'scale(0.6)', opacity: '0.4' },
          '40%': { transform: 'scale(1)', opacity: '1' },
        },
      },
      animation: {
        pulse: 'pulse 1.6s ease-in-out infinite',
        'fade-in': 'fadeIn 0.18s ease-out',
        'ticker-slide': 'tickerSlide 0.35s ease-out',
        'float-in': 'floatIn 0.35s ease-out',
      },
    },
  },
  plugins: [],
};

export default config;
