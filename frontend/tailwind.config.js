/** @type {import('tailwindcss').Config} */
export default {
  // Scan all JSX/JS files so Tailwind can tree-shake unused classes.
  content: [
    './index.html',
    './src/**/*.{js,jsx,ts,tsx}',
  ],
  theme: {
    extend: {
      // Add the monospace font stack used throughout the app.
      fontFamily: {
        mono: ['"JetBrains Mono"', '"Fira Code"', 'ui-monospace', 'monospace'],
      },
    },
  },
  plugins: [],
};
