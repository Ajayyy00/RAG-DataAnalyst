/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
      },
      colors: {
        'bg-primary': '#0a0f1e',
        'bg-surface': '#111827',
        'bg-elevated': '#1f2937',
        'accent': '#6366f1',
        'accent-hover': '#4f46e5',
      },
      animation: {
        'fade-in': 'fadeIn 0.3s ease forwards',
      },
    },
  },
  plugins: [],
}
