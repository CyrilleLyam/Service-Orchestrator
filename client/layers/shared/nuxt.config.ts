import { createResolver } from 'nuxt/kit'

const { resolve } = createResolver(import.meta.url)

export default defineNuxtConfig({
  $meta: {
    name: 'shared'
  },
  css: [resolve('./app/assets/css/main.css')]
})
