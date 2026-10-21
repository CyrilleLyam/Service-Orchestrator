import withNuxt from './.nuxt/eslint.config.mjs'
import betterTailwindcss from 'eslint-plugin-better-tailwindcss'
import { getDefaultAttributes } from 'eslint-plugin-better-tailwindcss/api/defaults'
import * as nuxtLayers from 'eslint-plugin-nuxt-layers'

const layerBoundaries = nuxtLayers.rules['layer-boundaries']
const layersPlugin = {
  rules: {
    'layer-boundaries': {
      ...layerBoundaries,
      create(context) {
        return layerBoundaries.create(Object.assign(Object.create(context), {
          getFilename: () => context.filename
        }))
      }
    }
  }
}

export default withNuxt(
  betterTailwindcss.configs['correctness-error'],
  {
    files: ['layers/**/*.{ts,js,vue}'],
    rules: {
      'no-restricted-imports': ['error', {
        patterns: [{
          group: ['~', '~/**', '@', '@/**', '~~', '~~/**', '@@', '@@/**', '../**'],
          message: 'Use #layers aliases instead of root aliases or parent-relative imports so layer boundaries can be checked.'
        }]
      }]
    }
  },
  {
    plugins: {
      'nuxt-layers': layersPlugin
    },
    rules: {
      'nuxt-layers/layer-boundaries': ['error', {
        root: 'layers',
        aliases: ['#layers'],
        layers: {
          shared: [],
          catalog: ['shared'],
          applications: ['shared']
        }
      }]
    },
    settings: {
      'better-tailwindcss': {
        entryPoint: 'layers/shared/app/assets/css/main.css',
        attributes: [
          ...getDefaultAttributes(),
          ['^v-bind:ui$', [{ match: 'objectValues' }]]
        ]
      }
    }
  }
)
