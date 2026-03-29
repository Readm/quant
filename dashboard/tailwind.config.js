/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: '#0a0f1e',
        secondary: '#111827',
        card: '#1a2235',
        border: '#1e293b',
      },
    },
  },
  plugins: [],
}
