<script setup lang="ts">
import type { FieldError, JsonObject } from '~/shared/types/api'
import { parseObject } from '~/shared/composables/useApi'
import { formLayout } from '~/shared/utils/schemaForm'
import SchemaForm from '~/shared/components/SchemaForm.vue'

const props = withDefaults(defineProps<{ definition: JsonObject, modelValue: string, errors?: FieldError[], disabled?: boolean }>(), { errors: () => [], disabled: false })
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const raw = ref(false)
const layout = computed(() => formLayout(props.definition))
const parsed = computed(() => {
  try {
    return parseObject(props.modelValue)
  } catch {
    return null
  }
})
const jsonMode = computed(() => raw.value || Boolean(layout.value.fallback) || !parsed.value)
function update(value: JsonObject) {
  emit('update:modelValue', JSON.stringify(value, null, 2))
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <p class="text-xs text-muted">
        Save partial answers as a draft. Validate or get a quote when ready.
      </p>
      <UButton
        v-if="!layout.fallback && parsed"
        :label="raw ? 'Use form' : 'Edit JSON'"
        variant="link"
        size="sm"
        :disabled="disabled"
        @click="raw = !raw"
      />
    </div>
    <p
      v-if="layout.fallback"
      class="text-sm text-muted"
    >
      {{ layout.fallback }} Your data is preserved.
    </p>
    <SchemaForm
      v-if="!jsonMode && parsed"
      :definition="definition"
      :model-value="parsed"
      :errors="errors"
      :disabled="disabled"
      @update:model-value="update"
    />
    <UFormField
      v-else
      label="Application data JSON"
      description="Enter the complete data object. Remove a property to delete its saved value."
    >
      <UTextarea
        :model-value="modelValue"
        :rows="12"
        :disabled="disabled"
        spellcheck="false"
        class="w-full font-mono"
        @update:model-value="emit('update:modelValue', $event)"
      />
    </UFormField>
  </div>
</template>
