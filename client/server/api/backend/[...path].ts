export default defineEventHandler((event) => {
  const config = useRuntimeConfig(event)
  const incoming = getRequestURL(event)
  const path = incoming.pathname.replace(/^\/api\/backend/, '')
  return proxyRequest(event, `${config.backendUrl}${path}${incoming.search}`)
})
