export default defineNuxtConfig({
  modules: [
    '@nuxt/eslint',
    '@nuxt/ui'
  ],

  components: [],

  imports: {
    scan: false
  },

  devtools: {
    enabled: true
  },
  runtimeConfig: {
    backendUrl: 'http://localhost:8000'
  },

  compatibilityDate: '2026-06-30',

  eslint: {
    config: {
      stylistic: {
        commaDangle: 'never',
        braceStyle: '1tbs'
      }
    }
  }
})
