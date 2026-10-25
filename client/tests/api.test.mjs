import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'
import axios from 'axios'

const source = await readFile(new URL('../app/shared/composables/useApi.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
function setup(adapter = async () => ({}), headers = {}) {
  const exports = {}
  const transport = {
    ...axios,
    create: config => axios.create({ ...config, adapter })
  }
  vm.runInNewContext(compiled, {
    exports,
    require: (name) => {
      assert.equal(name, 'axios')
      return { __esModule: true, default: transport }
    },
    useRequestURL: () => new URL('http://client.test/services'),
    useRequestHeaders: () => headers,
    URL,
    Error,
    JSON
  })
  return exports
}

test('preserves pagination, camelCase bodies and idempotency headers', async () => {
  const response = { error: false, data: [{ serviceCode: 'delivery' }], pagination: { page: 2, totalPages: 3 } }
  let called
  const { useApi } = setup(async (config) => {
    called = config
    return { data: response, status: 200, headers: {}, config }
  })
  const options = { method: 'POST', body: { serviceCode: 'delivery', data: {} }, headers: { 'Idempotency-Key': 'retry-key' } }
  assert.equal(await useApi()('/v1/applications', options), response)
  assert.equal(axios.getUri(called), 'http://client.test/api/backend/v1/applications')
  assert.deepEqual(JSON.parse(called.data), options.body)
  assert.equal(called.headers.get('Idempotency-Key'), 'retry-key')
  assert.equal(called.timeout, 15000)
})

test('retains structured backend field errors and request IDs on failed requests', async () => {
  const detail = { code: 'submission_rejected', message: 'Invalid payload', errors: [{ path: '/weightKg', message: 'Required' }], requestId: 'trace-1' }
  const { useApi, ApiError } = setup(async () => {
    throw new axios.AxiosError('Unprocessable Entity', 'ERR_BAD_REQUEST', undefined, undefined, {
      status: 422, data: { error: true, data: detail }
    })
  })
  await assert.rejects(useApi()('/v1/applications/id/submit'), error => error instanceof ApiError && error.detail === detail)
})

test('rejects an error envelope even if HTTP transport succeeds', async () => {
  const { useApi, ApiError } = setup(async () => ({ data: { error: true, data: { message: 'Conflict', errors: [] } }, status: 200 }))
  await assert.rejects(useApi()('/v1/services'), ApiError)
})

test('connection failures provide a useful message and preserve the cause', async () => {
  const cause = new Error('Connection refused')
  const { useApi } = setup(async () => {
    throw cause
  })
  await assert.rejects(useApi()('/v1/services'), error => error.cause === cause && /backend is running/.test(error.message))
})

test('JSON editors accept objects and reject malformed JSON, arrays, scalars and null', () => {
  const { parseObject } = setup()
  assert.deepEqual(parseObject('{"nested":{"value":null}}'), { nested: { value: null } })
  for (const value of ['{', '[]', 'null', '42', '"text"']) assert.throws(() => parseObject(value))
})

test('server proxy retains the request event and pagination query on a fixed backend origin', async () => {
  const source = await readFile(new URL('../server/api/backend/[...path].ts', import.meta.url), 'utf8')
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
  const exports = {}
  const event = { method: 'PATCH', headers: { 'Content-Type': 'application/merge-patch+json' }, body: { data: { notes: null } } }
  vm.runInNewContext(compiled, {
    exports,
    defineEventHandler: handler => handler,
    useRuntimeConfig: () => ({ backendUrl: 'http://localhost:8000' }),
    getRequestURL: () => new URL('http://client.test/api/backend/v1/applications/example?page=2&pageSize=12'),
    proxyRequest: (received, target) => ({ received, target })
  })
  const result = exports.default(event)
  assert.equal(result.received, event)
  assert.equal(result.target, 'http://localhost:8000/v1/applications/example?page=2&pageSize=12')
})

test('SSR credentials stay scoped to each Axios instance', async () => {
  const seen = []
  const adapter = async (config) => {
    seen.push(config.headers.get('Authorization'))
    return { status: 200, data: { error: false, data: {} }, headers: {}, config }
  }
  const first = setup(adapter, { authorization: 'Bearer first' }).useApi()
  const second = setup(adapter, { authorization: 'Bearer second' }).useApi()
  await first('/v1/services')
  await second('/v1/services')
  await first('/v1/services')
  assert.deepEqual(seen, ['Bearer first', 'Bearer second', 'Bearer first'])
})

test('merge-patch content type and null deletions survive Axios serialization', async () => {
  let sent
  const { useApi } = setup(async (config) => {
    sent = config
    return { status: 200, data: { error: false, data: {} }, headers: {}, config }
  })
  await useApi()('/v1/applications/example', {
    method: 'PATCH',
    body: { data: { notes: null } },
    headers: { 'Content-Type': 'application/merge-patch+json' }
  })
  assert.equal(sent.method, 'patch')
  assert.equal(sent.headers.get('Content-Type'), 'application/merge-patch+json')
  assert.deepEqual(JSON.parse(sent.data), { data: { notes: null } })
})
