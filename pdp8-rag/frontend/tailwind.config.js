/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      animation: {
        'fadeIn': 'fadeIn 0.5s ease-out',
        'slideInLeft': 'slideInLeft 0.3s ease-out',
        'slideInRight': 'slideInRight 0.3s ease-out',
        'slideInUp': 'slideInUp 0.2s ease-out',
        'slideInDown': 'slideInDown 0.2s ease-out',
        'scaleIn': 'scaleIn 0.2s ease-out',
        'shimmer': 'shimmer 2s infinite',
        'typing': 'typing 1.4s infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideInLeft: {
          '0%': { 
            opacity: '0',
            transform: 'translateX(-20px)',
          },
          '100%': { 
            opacity: '1',
            transform: 'translateX(0)',
          },
        },
        slideInRight: {
          '0%': { 
            opacity: '0',
            transform: 'translateX(20px)',
          },
          '100%': { 
            opacity: '1',
            transform: 'translateX(0)',
          },
        },
        slideInUp: {
          '0%': { 
            opacity: '0',
            transform: 'translateY(10px)',
          },
          '100%': { 
            opacity: '1',
            transform: 'translateY(0)',
          },
        },
        slideInDown: {
          '0%': { 
            opacity: '0',
            transform: 'translateY(-10px)',
          },
          '100%': { 
            opacity: '1',
            transform: 'translateY(0)',
          },
        },
        scaleIn: {
          '0%': { 
            opacity: '0',
            transform: 'scale(0.9)',
          },
          '100%': { 
            opacity: '1',
            transform: 'scale(1)',
          },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        typing: {
          '0%, 60%, 100%': { 
            transform: 'translateY(0)',
            opacity: '0.8',
          },
          '30%': { 
            transform: 'translateY(-10px)',
            opacity: '1',
          },
        },
      },
      colors: {
        gray: {
          750: '#2d3748',
          850: '#1a202e',
        },
      },
    },
  },
  plugins: [],
}