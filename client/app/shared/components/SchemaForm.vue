<script setup lang="ts">
import type { FieldError, JsonObject } from '~/shared/types/api'
import { cleanHiddenFields, errorsFor, fieldState, fieldValue, formLayout, isObject, setField } from '~/shared/utils/schemaForm'
import type { FormField } from '~/shared/utils/schemaForm'

const props = withDefaults(defineProps<{ definition: JsonObject, modelValue: JsonObject, errors?: FieldError[], disabled?: boolean }>(), { errors: () => [], disabled: false })
const emit = defineEmits<{ 'update:modelValue': [value: JsonObject] }>()
const layout = computed(() => formLayout(props.definition))
const uid = useId()
const fieldId = (field: FormField) => `${uid}-${field.pointer}`
function update(field: FormField, value: unknown) {
  emit('update:modelValue', cleanHiddenFields(props.definition, setField(props.modelValue, field.path, value)))
}
function input(field: FormField, event: Event) {
  const value = (event.target as HTMLInputElement).value
  update(field, value === '' ? undefined : ['number', 'integer'].includes(String(field.schema.type)) ? Number(value) : value)
}
function options(field: FormField): unknown[] {
  const items = field.schema.type === 'array' && isObject(field.schema.items) ? field.schema.items : field.schema
  return Array.isArray(items.enum) ? items.enum : []
}
function selected(field: FormField, value: unknown): boolean {
  const current = fieldValue(props.modelValue, field.path)
  return Array.isArray(current) && current.includes(value)
}
function toggle(field: FormField, value: unknown, checked: boolean) {
  const current = fieldValue(props.modelValue, field.path)
  const values = Array.isArray(current) ? current : []
  update(field, checked ? [...values, value] : values.filter(item => item !== value))
}
function select(field: FormField, event: Event) {
  const value = (event.target as HTMLSelectElement).value
  update(field, value === '' ? undefined : options(field)[Number(value)])
}
const inputType = (field: FormField) => ['number', 'integer'].includes(String(field.schema.type)) ? 'number' : field.schema.format === 'date' ? 'date' : field.schema.format === 'email' ? 'email' : 'text'
</script>

<template>
  <div class="space-y-6">
    <fieldset
      v-for="(section, index) in layout.sections"
      :key="index"
      :disabled="disabled"
      class="space-y-4"
    >
      <legend class="mb-3 font-semibold">
        {{ section.title }}
      </legend>
      <template
        v-for="field in section.fields"
        :key="field.path"
      >
        <div
          v-if="fieldState(definition, modelValue, field).visible"
          class="space-y-2"
        >
          <label
            :for="fieldId(field)"
            class="block text-sm font-medium"
          >
            {{ field.label }}<span
              v-if="fieldState(definition, modelValue, field).required"
              class="text-error"
            > *</span>
          </label>
          <p
            v-if="typeof field.schema.description === 'string'"
            :id="`${fieldId(field)}-description`"
            class="text-xs text-muted"
          >
            {{ field.schema.description }}
          </p>
          <div
            v-if="field.schema.type === 'array'"
            :id="fieldId(field)"
            role="group"
            :aria-label="field.label"
            class="space-y-2"
          >
            <label
              v-for="(option, optionIndex) in options(field)"
              :key="optionIndex"
              class="flex items-center gap-2 text-sm"
            >
              <input
                type="checkbox"
                :checked="selected(field, option)"
                :aria-describedby="errorsFor(field, errors) ? `${fieldId(field)}-error` : undefined"
                @change="toggle(field, option, ($event.target as HTMLInputElement).checked)"
              >
              {{ String(option) }}
            </label>
          </div>
          <div
            v-else-if="field.widget === 'radio' && options(field).length"
            :id="fieldId(field)"
            role="radiogroup"
            :aria-label="field.label"
            class="space-y-2"
          >
            <label
              v-for="(option, optionIndex) in options(field)"
              :key="optionIndex"
              class="flex items-center gap-2 text-sm"
            >
              <input
                type="radio"
                :name="fieldId(field)"
                :aria-describedby="errorsFor(field, errors) ? `${fieldId(field)}-error` : undefined"
                :checked="fieldValue(modelValue, field.path) === option"
                @change="update(field, option)"
              >
              {{ String(option) }}
            </label>
            <UButton
              v-if="fieldValue(modelValue, field.path) !== undefined"
              label="Clear selection"
              size="xs"
              variant="link"
              @click="update(field, undefined)"
            />
          </div>
          <select
            v-else-if="options(field).length"
            :id="fieldId(field)"
            :value="fieldValue(modelValue, field.path) === undefined ? '' : String(options(field).indexOf(fieldValue(modelValue, field.path)))"
            :aria-invalid="Boolean(errorsFor(field, errors))"
            :aria-describedby="errorsFor(field, errors) ? `${fieldId(field)}-error` : undefined"
            class="w-full rounded-md border border-default bg-default px-3 py-2 text-sm"
            @change="select(field, $event)"
          >
            <option value="">
              Choose an option
            </option>
            <option
              v-for="(option, optionIndex) in options(field)"
              :key="optionIndex"
              :value="String(optionIndex)"
            >
              {{ String(option) }}
            </option>
          </select>
          <USwitch
            v-else-if="field.schema.type === 'boolean' && field.widget === 'switch'"
            :id="fieldId(field)"
            :model-value="fieldValue(modelValue, field.path) === true"
            :label="field.label"
            :disabled="disabled"
            :aria-describedby="errorsFor(field, errors) ? `${fieldId(field)}-error` : undefined"
            @update:model-value="update(field, Boolean($event))"
          />
          <UCheckbox
            v-else-if="field.schema.type === 'boolean'"
            :id="fieldId(field)"
            :model-value="fieldValue(modelValue, field.path) === true"
            :label="field.label"
            :disabled="disabled"
            @update:model-value="update(field, Boolean($event))"
          />
          <UTextarea
            v-else-if="field.widget === 'textarea'"
            :id="fieldId(field)"
            :model-value="String(fieldValue(modelValue, field.path) ?? '')"
            :maxlength="typeof field.schema.maxLength === 'number' ? field.schema.maxLength : undefined"
            :disabled="disabled"
            :aria-invalid="Boolean(errorsFor(field, errors))"
            :aria-describedby="errorsFor(field, errors) ? `${fieldId(field)}-error` : undefined"
            class="w-full"
            @update:model-value="update(field, $event === '' ? undefined : $event)"
          />
          <input
            v-else
            :id="fieldId(field)"
            :type="inputType(field)"
            :value="fieldValue(modelValue, field.path) ?? ''"
            :step="field.schema.type === 'integer' ? 1 : 'any'"
            :min="typeof field.schema.minimum === 'number' ? field.schema.minimum : undefined"
            :max="typeof field.schema.maximum === 'number' ? field.schema.maximum : undefined"
            :maxlength="typeof field.schema.maxLength === 'number' ? field.schema.maxLength : undefined"
            :aria-invalid="Boolean(errorsFor(field, errors))"
            :aria-describedby="errorsFor(field, errors) ? `${fieldId(field)}-error` : undefined"
            class="w-full rounded-md border border-default bg-default px-3 py-2 text-sm"
            @input="input(field, $event)"
          >
          <p
            v-if="errorsFor(field, errors)"
            :id="`${fieldId(field)}-error`"
            class="text-sm text-error"
            role="alert"
          >
            {{ errorsFor(field, errors) }}
          </p>
        </div>
      </template>
    </fieldset>
  </div>
</template>
