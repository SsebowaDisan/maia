import { defineConfig } from 'vite'
import path from 'path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [
    // The React and Tailwind plugins are both required for Make, even if
    // Tailwind is not being actively used – do not remove them
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      // Alias @ to the src directory
      '@': path.resolve(__dirname, './src'),
      '@maia/acp': path.resolve(__dirname, '../../packages/acp-js/src/index.ts'),
      '@maia/computer-use': path.resolve(__dirname, '../../packages/computer-use/src/index.ts'),
      '@maia/theatre': path.resolve(__dirname, '../../packages/theatre-react/src/index.ts'),
    },
  },

  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('react-pdf') || id.includes('pdfjs-dist')) {
            return 'pdf';
          }
          if (id.includes('/node_modules/marked/') || id.includes('/node_modules/katex/') || id.includes('/node_modules/yaml/')) {
            return 'content';
          }
          if (id.includes('@mui/') || id.includes('@emotion/')) {
            return 'mui';
          }
          if (id.includes('@radix-ui/') || id.includes('cmdk') || id.includes('vaul')) {
            return 'radix';
          }
          if (id.includes('react-dnd') || id.includes('react-resizable-panels') || id.includes('motion') || id.includes('sonner')) {
            return 'interaction';
          }
          if (id.includes('@xyflow/') || id.includes('elkjs') || id.includes('recharts')) {
            return 'visualization';
          }
          if (
            id.includes('/frontend/user_interface/src/app/components/agentDesktopScene/') ||
            id.includes('/frontend/user_interface/src/app/components/agentActivityPanel/')
          ) {
            return 'agent-ui';
          }
          if (id.includes('/frontend/user_interface/src/app/components/graph/') || id.includes('/frontend/user_interface/src/app/components/workflow/')) {
            return 'graph-ui';
          }
          if (
            id.includes('/packages/theatre-react/') ||
            id.includes('/packages/computer-use/') ||
            id.includes('/packages/acp-js/') ||
            id.includes('/packages/brain-runtime/')
          ) {
            return 'maia-sdk';
          }
          if (id.includes('/node_modules/')) {
            return 'vendor';
          }
        },
      },
    },
  },

  // File types to support raw imports. Never add .css, .tsx, or .ts files to this.
  assetsInclude: ['**/*.svg', '**/*.csv'],
})
