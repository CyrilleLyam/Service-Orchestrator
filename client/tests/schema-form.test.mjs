import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

const requireNuxt = createRequire(import.meta.resolve('nuxt'))
const vue = requireNuxt('vue')
const { parse, compileScript } = requireNuxt('vue/compiler-sfc')
const { renderToString } = requireNuxt('vue/server-renderer')
function compile(source, imports = {}) {
  const exports = {}
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  vm.runInNewContext(compiled, {
    exports,
    computed: vue.computed,
    useId: vue.useId,
    require: name => imports[name] ?? requireNuxt(name)
  })
  return exports
}
const source = await readFile(new URL('../app/shared/utils/schemaForm.ts', import.meta.url), 'utf8')
const helpers = compile(source)
const { formLayout, fieldState, fieldValue, setField, cleanHiddenFields, mergePatch, errorsFor, sameValue } = helpers
const componentSource = await readFile(new URL('../app/shared/components/SchemaForm.vue', import.meta.url), 'utf8')
const { descriptor } = parse(componentSource)
const component = compile(compileScript(descriptor, { id: 'schema-form', inlineTemplate: true }).content, { '~/shared/utils/schemaForm': helpers }).default
const examples = {}
for (const name of ['delivery_service', 'event_registration', 'equipment_rental']) {
  examples[name] = JSON.parse(await readFile(new URL(`../../backend/examples/${name}.json`, import.meta.url), 'utf8')).definition
}
const plain = value => JSON.parse(JSON.stringify(value))
const fieldsFor = definition => formLayout(definition).sections.flatMap(section => section.fields)
async function render(definition, data = {}, errors = []) {
  const app = vue.createSSRApp(component, { definition, modelValue: data, errors })
  for (const name of ['UCheckbox', 'USwitch']) app.component(name, {
    props: ['modelValue', 'id', 'label'],
    setup: props => () => vue.h('input', { 'type': 'checkbox', 'id': props.id, 'checked': props.modelValue, 'aria-label': props.label })
  })
  app.component('UTextarea', { props: ['modelValue'], setup: props => () => vue.h('textarea', props.modelValue) })
  app.component('UButton', { props: ['label'], setup: props => () => vue.h('button', props.label) })
  return renderToString(app)
}

test('all seeded schemas render without JSON fallback and honor UI section order', () => {
  for (const definition of Object.values(examples)) assert.equal(formLayout(definition).fallback, null)
  const layout = formLayout(examples.delivery_service)
  assert.deepEqual(plain(layout.sections.map(section => section.title)), ['Parcel', 'Anything else?'])
  assert.deepEqual(plain(layout.sections[0].fields.map(field => field.path)), ['distanceKm', 'weightKg', 'express'])
  assert.equal(fieldsFor(examples.equipment_rental).find(field => field.path === 'delivery.phone').pointer, '/delivery/phone')
})

test('attendee changes update conditional fields and remove hidden answers without mutation', () => {
  const definition = examples.event_registration
  const fields = fieldsFor(definition)
  const company = fields.find(field => field.path === 'companyName')
  const student = fields.find(field => field.path === 'studentId')
  const initial = { attendeeType: 'corporate', companyName: 'Acme', sessions: ['keynote'] }
  assert.deepEqual(plain(fieldState(definition, initial, company)), { visible: true, required: true })
  assert.equal(fieldState(definition, initial, student).visible, false)
  const changed = cleanHiddenFields(definition, setField(initial, 'attendeeType', 'student'))
  assert.equal(Object.hasOwn(changed, 'companyName'), false)
  assert.equal(initial.companyName, 'Acme')
  assert.deepEqual(plain(fieldState(definition, changed, student)), { visible: true, required: true })
  assert.deepEqual(plain(mergePatch(initial, changed)), { attendeeType: 'student', companyName: null })
})

test('nested editing preserves siblings and optional groups can be removed completely', () => {
  const initial = { insurance: false, delivery: { address: 'Phnom Penh', phone: '+855 12345678' } }
  const changed = setField(initial, 'delivery.address', 'Siem Reap')
  assert.equal(fieldValue(changed, 'delivery.phone'), initial.delivery.phone)
  assert.equal(initial.delivery.address, 'Phnom Penh')
  const removed = setField(setField(initial, 'delivery.address', undefined), 'delivery.phone', undefined)
  assert.deepEqual(plain(removed), { insurance: false })
  assert.deepEqual(plain(mergePatch(initial, removed)), { delivery: null })
  const address = fieldsFor(examples.equipment_rental).find(field => field.path === 'delivery.address')
  assert.equal(fieldState(examples.equipment_rental, {}, address).required, false)
  assert.equal(fieldState(examples.equipment_rental, { delivery: { phone: '123456' } }, address).required, true)
})

test('merge patch preserves false, zero, arrays and unchanged nulls, and reports unrepresentable null edits', () => {
  assert.deepEqual(plain(mergePatch({ n: 1, active: true, items: ['a'], unchanged: null }, { n: 0, active: false, items: [], unchanged: null })), { n: 0, active: false, items: [] })
  assert.deepEqual(plain(mergePatch({ contact: { email: 'old', phone: '123' } }, { contact: { email: 'new' } })), { contact: { email: 'new', phone: null } })
  assert.deepEqual(plain(mergePatch({}, { list: [null] })), { list: [null] })
  assert.throws(() => mergePatch({}, { value: null }), /cannot save a new null/)
  assert.throws(() => mergePatch({}, { contact: { email: null } }), /cannot save a new null/)
  assert.equal(sameValue({ a: 1, b: 2 }, { b: 2, a: 1 }), true)
  assert.equal(sameValue(true, 1), false)
})

test('complex schema types and unknown visibility conditions fall back to JSON', () => {
  for (const schema of [{ type: ['string', 'null'] }, { oneOf: [{ type: 'string' }] }, { $ref: '#/$defs/item' }, { type: 'array', items: { type: 'object' } }, { type: 'string', enum: [null, 'yes'] }]) {
    assert.ok(formLayout({ dataSchema: { type: 'object', additionalProperties: false, properties: { item: schema } } }).fallback)
  }
  assert.ok(formLayout({ dataSchema: { type: 'object', properties: {} } }).fallback)
  const definition = structuredClone(examples.event_registration)
  definition.rules[1].when = { '+': [1, 2] }
  assert.ok(formLayout(definition).fallback)
})

test('condition equality and truthiness match backend semantics for booleans and empty arrays', () => {
  const definition = structuredClone(examples.event_registration)
  const field = fieldsFor(definition).find(field => field.path === 'companyName')
  definition.rules = [{ type: 'visible', fields: ['companyName'], when: { '==': [{ var: 'answer' }, 1] } }]
  assert.equal(fieldState(definition, { answer: true }, field).visible, false)
  definition.rules[0].when = { '!!': [{ var: 'answer' }] }
  assert.equal(fieldState(definition, { answer: [] }, field).visible, false)
  assert.equal(fieldState(definition, { answer: {} }, field).visible, true)
})

test('field errors use escaped JSON pointers and include array item errors', () => {
  const field = fieldsFor(examples.event_registration).find(field => field.path === 'sessions')
  assert.equal(errorsFor(field, [{ path: '/sessions/0', message: 'Unknown session' }]), 'Unknown session')
  const escaped = fieldsFor({ dataSchema: { type: 'object', additionalProperties: false, properties: { 'a/b~c': { type: 'string' } } } })[0]
  assert.equal(escaped.pointer, '/a~1b~0c')
})

test('property paths cannot read or mutate inherited prototypes', () => {
  assert.equal(fieldValue({}, '__proto__.polluted'), undefined)
  const data = setField({}, '__proto__.polluted', true)
  assert.equal({}.polluted, undefined)
  assert.equal(fieldValue(data, '__proto__.polluted'), true)
})

test('rendered delivery form includes number inputs, errors, boolean and notes controls', async () => {
  const html = await render(examples.delivery_service, { distanceKm: 100, express: true }, [{ path: '/distanceKm', message: 'Express is limited to 50 km.' }])
  assert.equal((html.match(/type="number"/g) ?? []).length, 2)
  assert.match(html, /Express is limited to 50 km\./)
  assert.match(html, /aria-invalid="true"/)
  assert.match(html, /type="checkbox"[^>]*checked/)
  assert.match(html, /<textarea/)
})

test('rendered event form shows corporate fields and session choices', async () => {
  const html = await render(examples.event_registration, { attendeeType: 'corporate', sessions: ['keynote'] })
  assert.match(html, /type="email"/)
  assert.match(html, /type="radio"/)
  assert.match(html, /company Name/)
  assert.doesNotMatch(html, /student Id/)
  assert.equal((html.match(/type="checkbox"/g) ?? []).length, 3)
})

test('rendered rental form includes category, date, duration and nested delivery fields', async () => {
  const html = await render(examples.equipment_rental)
  assert.match(html, /<select/)
  assert.match(html, /type="date"/)
  assert.match(html, /step="1"/)
  assert.match(html, /delivery\/address/)
  assert.match(html, /delivery\/phone/)
})

// Exercise real component event handlers with Vue's host-independent renderer.
async function mountForm(definition, initial) {
  const node = (tag, text = '') => ({ tag, text, props: {}, children: [], parent: null })
  const renderer = vue.createRenderer({
    createElement: tag => node(tag),
    createText: text => node('#text', text),
    createComment: text => node('#comment', text),
    setText: (element, text) => { element.text = text },
    setElementText: (element, text) => {
      element.text = text
      element.children = []
    },
    patchProp: (element, key, _before, after) => { element.props[key] = after },
    parentNode: element => element.parent,
    nextSibling: element => element.parent?.children[element.parent.children.indexOf(element) + 1],
    insert: (element, parent, anchor) => {
      if (element.parent) element.parent.children.splice(element.parent.children.indexOf(element), 1)
      const index = anchor ? parent.children.indexOf(anchor) : -1
      parent.children.splice(index < 0 ? parent.children.length : index, 0, element)
      element.parent = parent
    },
    remove: (element) => {
      if (element.parent) element.parent.children.splice(element.parent.children.indexOf(element), 1)
    }
  })
  const model = vue.ref(initial)
  const app = renderer.createApp({
    setup: () => () => vue.h(component, { definition, 'modelValue': model.value, 'onUpdate:modelValue': (value) => { model.value = value } })
  })
  for (const name of ['UCheckbox', 'USwitch']) app.component(name, {
    props: ['modelValue', 'id'], emits: ['update:modelValue'],
    setup: (props, { emit }) => () => vue.h('input', { id: props.id, type: 'checkbox', checked: props.modelValue, onChange: event => emit('update:modelValue', event.target.checked) })
  })
  app.component('UTextarea', {
    props: ['modelValue', 'id'], emits: ['update:modelValue'],
    setup: (props, { emit }) => () => vue.h('textarea', { id: props.id, value: props.modelValue, onInput: event => emit('update:modelValue', event.target.value) })
  })
  app.component('UButton', { props: ['label'], setup: props => () => vue.h('button', props.label) })
  const root = node('root')
  app.mount(root)
  const all = (parent = root) => [parent, ...parent.children.flatMap(child => all(child))]
  return { model, find: predicate => all().find(predicate), all, unmount: () => app.unmount() }
}

test('delivery input events preserve numeric zero, booleans and textarea answers', async () => {
  const form = await mountForm(examples.delivery_service, { weightKg: 2 })
  form.find(node => node.props.id?.endsWith('/distanceKm')).props.onInput({ target: { value: '0' } })
  await vue.nextTick()
  form.find(node => node.props.id?.endsWith('/express')).props.onChange({ target: { checked: true } })
  await vue.nextTick()
  form.find(node => node.tag === 'textarea').props.onInput({ target: { value: 'Handle carefully' } })
  await vue.nextTick()
  assert.deepEqual(plain(form.model.value), { distanceKm: 0, weightKg: 2, express: true, notes: 'Handle carefully' })
  form.unmount()
})

test('attendee radio changes hide and delete the corporate answer in the rendered form', async () => {
  const form = await mountForm(examples.event_registration, { attendeeType: 'corporate', companyName: 'Acme', sessions: ['keynote'] })
  form.find(node => node.tag === 'input' && node.props.type === 'radio').props.onChange()
  await vue.nextTick()
  assert.equal(form.model.value.attendeeType, 'student')
  assert.equal(Object.hasOwn(form.model.value, 'companyName'), false)
  assert.ok(form.find(node => node.tag === 'input' && node.props.id?.endsWith('/studentId')))
  assert.equal(form.find(node => node.tag === 'input' && node.props.id?.endsWith('/companyName')), undefined)
  const sessionInputs = form.all().filter(node => node.tag === 'input' && node.props.type === 'checkbox')
  sessionInputs[1].props.onChange({ target: { checked: true } })
  await vue.nextTick()
  assert.deepEqual(plain(form.model.value.sessions), ['keynote', 'workshop-a'])
  form.unmount()
})

test('rental events preserve enum types and edit nested objects without losing siblings', async () => {
  const form = await mountForm(examples.equipment_rental, { delivery: { phone: '12345678' } })
  form.find(node => node.tag === 'select').props.onChange({ target: { value: '0' } })
  await vue.nextTick()
  form.find(node => node.props.id?.endsWith('/durationDays')).props.onInput({ target: { value: '10' } })
  await vue.nextTick()
  form.find(node => node.props.id?.endsWith('/startDate')).props.onInput({ target: { value: '2026-11-02' } })
  await vue.nextTick()
  form.find(node => node.props.id?.endsWith('/delivery/address')).props.onInput({ target: { value: 'Phnom Penh' } })
  await vue.nextTick()
  assert.deepEqual(plain(form.model.value), { equipmentCategory: 'camera', durationDays: 10, startDate: '2026-11-02', delivery: { phone: '12345678', address: 'Phnom Penh' } })
  form.unmount()
})

test('supported presentation conditions respect strict comparisons, membership and short circuiting', () => {
  const definition = structuredClone(examples.event_registration)
  const field = fieldsFor(definition).find(field => field.path === 'companyName')
  const data = { n: 2, text: 'abc', choices: ['a'], empty: [], nil: null }
  const cases = [
    [{ '<': [1, { var: 'n' }, 3] }, true],
    [{ '<=': [2, { var: 'n' }] }, true],
    [{ '>': [{ var: 'n' }, 1] }, true],
    [{ '>=': [{ var: 'n' }, 3] }, false],
    [{ '<': ['1', { var: 'n' }] }, false],
    [{ '!=': [{ var: 'n' }, '2'] }, true],
    [{ in: ['a', { var: 'choices' }] }, true],
    [{ in: ['ab', { var: 'text' }] }, true],
    [{ and: [true, { '!': [{ var: 'empty' }] }] }, true],
    [{ or: [{ var: 'empty' }, false] }, false],
    [{ if: [false, false, true, { '==': [{ var: ['nil', 2] }, 2] }, false] }, true],
    [{ '==': [[1, true], [1, 1]] }, false]
  ]
  for (const [when, expected] of cases) {
    definition.rules = [{ type: 'visible', fields: ['companyName'], when }]
    assert.equal(fieldState(definition, data, field).visible, expected, JSON.stringify(when))
  }
})

test('hidden-field cleanup resolves chained visibility and preserves other answers', () => {
  const definition = {
    rules: [
      { type: 'visible', when: { '!!': [{ var: 'a' }] }, fields: ['b'] },
      { type: 'visible', when: { '!!': [{ var: 'b' }] }, fields: ['c'] }
    ]
  }
  const data = { a: false, b: 'old', c: 'old', untouched: 0 }
  assert.deepEqual(plain(cleanHiddenFields(definition, data)), { a: false, untouched: 0 })
  assert.equal(data.b, 'old')
})
