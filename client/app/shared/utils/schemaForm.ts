import type { FieldError, JsonObject } from '~/shared/types/api'

type Schema = Record<string, unknown>
export interface FormField { path: string, pointer: string, label: string, schema: Schema, widget: string, required: boolean }
export interface FormSection { title: string, fields: FormField[] }
export interface FormLayout { sections: FormSection[], fallback: string | null }
const has = (object: object, key: string) => Object.prototype.hasOwnProperty.call(object, key)
export const isObject = (value: unknown): value is JsonObject => value !== null && typeof value === 'object' && !Array.isArray(value)
export function localized(value: unknown, fallback: string): string {
  if (typeof value === 'string') return value
  if (isObject(value)) return String(value.en ?? Object.values(value)[0] ?? fallback)
  return fallback
}
export function fieldValue(data: unknown, path: string): unknown {
  let value = data
  for (const key of path.split('.')) {
    if (!isObject(value) || !has(value, key)) return undefined
    value = value[key]
  }
  return value
}
export function setField(data: JsonObject, path: string, value: unknown): JsonObject {
  const [key = '', ...rest] = path.split('.')
  const result = { ...data }
  const next = rest.length ? setField(isObject(data[key]) ? data[key] : {}, rest.join('.'), value) : value
  if (next === undefined || (rest.length && isObject(next) && !Object.keys(next).length)) Reflect.deleteProperty(result, key)
  else Object.defineProperty(result, key, { value: next, enumerable: true, writable: true, configurable: true })
  return result
}
export function sameValue(a: unknown, b: unknown): boolean {
  if (Array.isArray(a) && Array.isArray(b)) return a.length === b.length && a.every((value, index) => sameValue(value, b[index]))
  if (isObject(a) && isObject(b)) return Object.keys(a).length === Object.keys(b).length && Object.keys(a).every(key => has(b, key) && sameValue(a[key], b[key]))
  return a === b
}
const truthy = (value: unknown) => Array.isArray(value) ? value.length > 0 : Boolean(value)
const uiOperators = new Set(['var', '==', '!=', 'and', 'or', '!', '!!', 'in', '<', '<=', '>', '>=', 'if'])
function supportedExpression(value: unknown, depth = 0): boolean {
  if (depth > 16) return false
  if (Array.isArray(value)) return value.every(item => supportedExpression(item, depth + 1))
  if (!isObject(value)) return true
  const entries = Object.entries(value)
  return entries.length === 1 && uiOperators.has(entries[0]![0]) && supportedExpression(entries[0]![1], depth + 1)
}
// Only presentation conditions run here. The server remains authoritative for validation and fees.
function evaluate(expression: unknown, data: JsonObject, depth = 0): unknown {
  if (depth > 16) throw new Error('Condition nesting exceeds the form limit.')
  if (Array.isArray(expression)) return expression.map(item => evaluate(item, data, depth + 1))
  if (!isObject(expression)) return expression
  const [op, raw] = Object.entries(expression)[0] ?? []
  const args = Array.isArray(raw) ? raw : [raw]
  if (op === 'var') {
    const path = Array.isArray(raw) ? raw[0] : raw
    return fieldValue(data, String(path)) ?? (Array.isArray(raw) ? raw[1] ?? null : null)
  }
  const run = (value: unknown) => evaluate(value, data, depth + 1)
  if (op === 'and' || op === 'or') {
    let result: unknown = null
    for (const arg of args) {
      result = run(arg)
      if (truthy(result) === (op === 'or')) return result
    }
    return result
  }
  if (op === 'if') {
    for (let index = 0; index < args.length - 1; index += 2) {
      if (truthy(run(args[index]))) return run(args[index + 1])
    }
    return args.length % 2 ? run(args.at(-1)) : null
  }
  const values = args.map(run)
  const [a, b] = values
  if (op === '==') return sameValue(a, b)
  if (op === '!=') return !sameValue(a, b)
  if (op === '!') return !truthy(a)
  if (op === '!!') return truthy(a)
  if (op === 'in') return Array.isArray(b) ? b.some(item => sameValue(a, item)) : typeof a === 'string' && typeof b === 'string' && b.includes(a)
  if (['<', '<=', '>', '>='].includes(op ?? '')) {
    if (!values.every(value => typeof value === 'number') && !values.every(value => typeof value === 'string')) return false
    return values.slice(1).every((value, index) => {
      const left = values[index] as number
      const right = value as number
      if (op === '<') return left < right
      if (op === '<=') return left <= right
      if (op === '>') return left > right
      return left >= right
    })
  }
  throw new Error('Unsupported form condition.')
}
function rules(definition: JsonObject): JsonObject[] {
  return Array.isArray(definition.rules) ? definition.rules.filter(isObject) : []
}
export function fieldState(definition: JsonObject, data: JsonObject, field: FormField) {
  let visible = true
  const parent = field.path.split('.').slice(0, -1).join('.')
  let required = field.required && (!parent || isObject(fieldValue(data, parent)))
  for (const rule of rules(definition)) {
    if (!Array.isArray(rule.fields) || !rule.fields.some(path => typeof path === 'string' && (path === field.path || field.path.startsWith(`${path}.`)))) continue
    const applies = rule.when === undefined || truthy(evaluate(rule.when, data))
    if (rule.type === 'visible' && !applies) visible = false
    if (rule.type === 'require' && applies) required = true
  }
  return { visible, required }
}
export function cleanHiddenFields(definition: JsonObject, data: JsonObject): JsonObject {
  let result = data
  // Re-evaluate chained conditions until stable; never run unknown conditions in JSON mode.
  for (let pass = 0; pass <= rules(definition).length; pass++) {
    let next = result
    for (const rule of rules(definition)) {
      if (rule.type !== 'visible' || !supportedExpression(rule.when)) continue
      if (rule.when !== undefined && !truthy(evaluate(rule.when, result)) && Array.isArray(rule.fields)) {
        for (const path of rule.fields) if (typeof path === 'string') next = setField(next, path, undefined)
      }
    }
    if (sameValue(next, result)) return next
    result = next
  }
  return result
}
export function formLayout(definition: JsonObject): FormLayout {
  const schema = definition.dataSchema
  const ui = isObject(definition.uiSchema) ? definition.uiSchema : {}
  const hints = isObject(ui.fields) ? ui.fields : {}
  const fields: FormField[] = []
  let fallback: string | null = null
  const unsupported = ['$ref', '$dynamicRef', 'oneOf', 'anyOf', 'allOf', 'if', 'then', 'else', 'not', 'dependentSchemas', 'patternProperties']
  const visit = (node: unknown, path: string, pointer: string, required: boolean, depth: number) => {
    if (!isObject(node) || depth > 12 || unsupported.some(key => has(node, key))) {
      fallback = 'This schema uses features that need the JSON editor.'
      return
    }
    if (node.type === 'object') {
      if (node.additionalProperties !== false || !isObject(node.properties)) {
        fallback = 'Objects with arbitrary properties need the JSON editor.'
        return
      }
      for (const [key, child] of Object.entries(node.properties)) {
        if (key.includes('.') || !key) {
          fallback = 'These property names need the JSON editor.'
          continue
        }
        visit(child, path ? `${path}.${key}` : key, `${pointer}/${key.replace(/~/g, '~0').replace(/\//g, '~1')}`, Array.isArray(node.required) && node.required.includes(key), depth + 1)
      }
      return
    }
    const enumValues = Array.isArray(node.enum) ? node.enum : null
    const arrayItems = node.type === 'array' && isObject(node.items) ? node.items : null
    const options = enumValues ?? (arrayItems && Array.isArray(arrayItems.enum) ? arrayItems.enum : null)
    if (options ? options.length > 0 && options.every(item => ['string', 'number', 'boolean'].includes(typeof item)) : ['string', 'number', 'integer', 'boolean'].includes(String(node.type))) {
      const hint = isObject(hints[path]) ? hints[path] : {}
      fields.push({ path, pointer, label: localized(node.title, path.split('.').at(-1)!.replace(/([a-z])([A-Z])/g, '$1 $2')), schema: node, widget: String(hint.widget ?? ''), required })
    } else fallback = 'This field type needs the JSON editor.'
  }
  visit(schema, '', '', false, 0)
  if (rules(definition).some(rule => ['visible', 'require'].includes(String(rule.type)) && rule.when !== undefined && !supportedExpression(rule.when))) fallback = 'This service uses conditions that need the JSON editor.'
  const byPath = new Map(fields.map(field => [field.path, field]))
  const used = new Set<string>()
  const sections: FormSection[] = []
  if (Array.isArray(ui.steps)) {
    for (const step of ui.steps.filter(isObject)) {
      const selected: FormField[] = []
      for (const path of Array.isArray(step.fields) ? step.fields : []) {
        for (const field of fields) {
          if ((field.path === path || field.path.startsWith(`${path}.`)) && !used.has(field.path)) {
            selected.push(field)
            used.add(field.path)
          }
        }
      }
      if (selected.length) sections.push({ title: localized(step.title, String(step.id ?? 'Details')), fields: selected })
    }
  }
  const remaining = [...byPath.values()].filter(field => !used.has(field.path))
  if (remaining.length) sections.push({ title: sections.length ? 'Other details' : 'Details', fields: remaining })
  return { sections, fallback }
}
export function errorsFor(field: FormField, errors: FieldError[]): string {
  return errors.filter(error => error.path === field.pointer || error.path.startsWith(`${field.pointer}/`)).map(error => error.message).join(' ')
}
export function mergePatch(before: JsonObject, after: JsonObject): JsonObject {
  const entries: [string, unknown][] = []
  for (const key of new Set([...Object.keys(before), ...Object.keys(after)])) {
    if (!has(after, key)) {
      entries.push([key, null])
      continue
    }
    if (has(before, key) && sameValue(before[key], after[key])) continue
    if (after[key] === null) throw new Error('JSON Merge Patch cannot save a new null value in an object. Remove the field instead.')
    entries.push([key, isObject(after[key]) ? mergePatch(isObject(before[key]) ? before[key] : {}, after[key]) : after[key]])
  }
  return Object.fromEntries(entries)
}
