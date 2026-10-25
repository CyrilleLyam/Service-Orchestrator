import withNuxt from './.nuxt/eslint.config.mjs'
import betterTailwindcss from 'eslint-plugin-better-tailwindcss'
import { getDefaultAttributes } from 'eslint-plugin-better-tailwindcss/api/defaults'

export default withNuxt(
  betterTailwindcss.configs['correctness-error'],
  ...['shared', 'features/catalog', 'features/applications'].map(folder => ({
    files: [`app/${folder}/**/*.{ts,js,vue}`],
    rules: {
      'no-restricted-imports': ['error', {
        patterns: [{
          group: [
            ...(folder === 'shared'
              ? ['~/features/**', '@/features/**']
              : [
                  `~/features/${folder.endsWith('catalog') ? 'applications' : 'catalog'}/**`,
                  `@/features/${folder.endsWith('catalog') ? 'applications' : 'catalog'}/**`
                ]),
            '~/pages/**', '@/pages/**', '~/app.vue', '@/app.vue', '../**', '~~/**', '@@/**'
          ],
          message: 'Keep features independent and shared code feature-free. Use explicit ~/ imports.'
        }]
      }]
    }
  })),
  {
    settings: {
      'better-tailwindcss': {
        entryPoint: 'app/assets/css/main.css',
        attributes: [
          ...getDefaultAttributes(),
          ['^v-bind:ui$', [{ match: 'objectValues' }]]
        ]
      }
    }
  }
)
