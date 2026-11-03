/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./core/templates/**/*.html",
    "./**/templates/**/*.html",
  ],
  theme: {
    extend: {
      fontFamily: {
        // Espaço reservado para fontes customizadas futuras
        sans: ['Inter', 'sans-serif'],
      },
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
  ],
}