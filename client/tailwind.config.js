/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        sda: {
          blue: '#1b365d',
          gold: '#cda851',
          navy: '#0f2038',
          accent: '#2b548b',
          light: '#f4f6fa'
        }
      }
    },
  },
  plugins: [],
}

