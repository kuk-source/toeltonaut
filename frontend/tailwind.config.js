/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        vulkan:        '#1A1A2E',
        lava:          '#2D2D3A',
        gletscherblau: '#A8D8EA',
        islandblau:    '#003F87',
        nordlicht:     '#00C896',
        geysirweiss:   '#F0F4F8',
        flaggenrot:    '#C8102E',
        'flaggenrot-text': '#FF6B81',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
