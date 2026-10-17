/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        'erp-orange': '#ff5e2c',
        'erp-vanilla': '#fff6c0',
        'erp-tangerine': '#F28B0C',
        'erp-tenne': '#D95204',
        'erp-dark-vanilla': '#D9BBA9',
        'erp-topaz': '#8C2703',
        'erp-chocolate': '#400101',
        'vanilla-bg': '#FBF6EB',
        'vanilla-surface': '#F4ECD9',
        'ink-text': '#1C140F',
        'burnt-orange': '#D95D39',
        'burnt-orange-dark': '#C44D29',
        'brand-navy': '#1B3A5C',
        'brand-steel': '#3E7CB1',
        'brand-offwhite': '#FBF6EB',
        'brand-charcoal': '#1C140F',
      },
    },
  },
  plugins: [],
};
