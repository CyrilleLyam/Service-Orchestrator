<script setup lang="ts">
import { ApiError, parseObject, useApi } from '~/shared/composables/useApi'
import type { Application, Quote, Service, Validation, Version } from '~/shared/types/api'
import ApiFeedback from '~/shared/components/ApiFeedback.vue'
import FeeSummary from '~/shared/components/FeeSummary.vue'
import ApplicationDataEditor from '~/shared/components/ApplicationDataEditor.vue'

const props = defineProps<{ code: string }>()
const emit = defineEmits<{ applicationCreated: [id: string] }>()
const api = useApi()
const base = `/v1/services/${encodeURIComponent(props.code)}`
const { data: response, error: loadError, refresh } = await useAsyncData(`service:${props.code}`, () => api<Service>(base))
const service = computed(() => response.value?.data)
const selected = ref<Version | null>(service.value?.published ?? null)
const definition = ref(JSON.stringify(selected.value?.definition ?? { dataSchema: { type: 'object', properties: {} }, rules: [], fees: [], uiSchema: {} }, null, 2))
const payload = ref('{}')
const busy = ref(false)
const error = shallowRef<unknown>(null)
const notice = ref('')
const validation = ref<Validation | null>(null)
const quote = ref<Quote | null>(null)
const fieldErrors = computed(() => error.value instanceof ApiError ? error.value.detail.errors : validation.value?.errors ?? [])
const creationKey = ref('')
const creationBody = ref('')
async function run(action: () => Promise<void>) {
  if (busy.value) return
  busy.value = true
  error.value = null
  notice.value = ''
  try {
    await action()
  } catch (e) {
    error.value = e
  } finally {
    busy.value = false
  }
}
function showVersion(version: Version) {
  selected.value = version
  definition.value = JSON.stringify(version.definition, null, 2)
}
function readVersion(version: number) {
  return run(async () => {
    showVersion((await api<Version>(`${base}/versions/${version}`)).data)
  })
}
function createVersion() {
  return run(async () => {
    showVersion((await api<Version>(`${base}/versions`, { method: 'POST', body: { definition: parseObject(definition.value) } })).data)
    await refresh()
    notice.value = 'Draft version created.'
  })
}
function saveVersion() {
  return run(async () => {
    if (!selected.value) return
    showVersion((await api<Version>(`${base}/versions/${selected.value.version}`, { method: 'PUT', body: { definition: parseObject(definition.value) } })).data)
    await refresh()
    notice.value = 'Definition saved.'
  })
}
function publish() {
  return run(async () => {
    if (!selected.value) return
    if (JSON.stringify(parseObject(definition.value)) !== JSON.stringify(selected.value.definition)) throw new Error('Save your definition before publishing.')
    showVersion((await api<Version>(`${base}/versions/${selected.value.version}/publish`, { method: 'POST' })).data)
    await refresh()
    notice.value = 'Version published. New applications will use this version.'
  })
}
function check(kind: 'validate' | 'quote') {
  return run(async () => {
    validation.value = null
    quote.value = null
    const body = { data: parseObject(payload.value) }
    if (kind === 'validate') validation.value = (await api<Validation>(`${base}/validate`, { method: 'POST', body })).data
    else quote.value = (await api<Quote>(`${base}/quote`, { method: 'POST', body })).data
  })
}
function createApplication() {
  return run(async () => {
    const body = { serviceCode: props.code, data: parseObject(payload.value) }
    const serialized = JSON.stringify(body)
    if (!creationKey.value || creationBody.value !== serialized) {
      creationKey.value = crypto.randomUUID()
      creationBody.value = serialized
    }
    const result = await api<Application>('/v1/applications', { method: 'POST', body, headers: { 'Idempotency-Key': creationKey.value } })
    emit('applicationCreated', result.data.id)
  })
}
watch(payload, () => {
  validation.value = null
  quote.value = null
  error.value = null
})
watch(() => service.value?.published?.version, () => {
  validation.value = null
  quote.value = null
})
</script>

<template>
  <div class="space-y-6">
    <UButton
      to="/"
      label="Service catalog"
      icon="i-lucide-arrow-left"
      variant="link"
    />
    <ApiFeedback :error="loadError" />
    <template v-if="service">
      <div>
        <h1 class="text-3xl font-bold">
          {{ service.name }}
        </h1><p class="mt-2 text-muted">
          {{ service.description }}
        </p><p class="mt-2 text-sm text-primary">
          {{ service.code }} · {{ service.published ? `Published v${service.published.version}` : 'Not published' }}
        </p>
      </div>
      <ApiFeedback :error="error" /><p
        v-if="notice"
        role="status"
        class="text-sm text-success"
      >
        {{ notice }}
      </p>
      <div class="grid items-start gap-6 lg:grid-cols-2">
        <UCard>
          <template #header>
            <h2 class="font-semibold">
              Service definition
            </h2>
          </template>
          <div class="space-y-4">
            <div class="flex flex-wrap gap-2">
              <UButton
                v-for="version in service.versions"
                :key="version.version"
                :label="`v${version.version} · ${version.status}`"
                :variant="selected?.version === version.version ? 'solid' : 'outline'"
                :disabled="busy"
                @click="readVersion(version.version)"
              />
            </div>
            <p class="text-sm text-muted">
              {{ selected ? `Viewing version ${selected.version}. Published definitions are immutable.` : 'Start with a JSON definition containing dataSchema, rules, fees and uiSchema.' }}
            </p>
            <UFormField label="Definition JSON">
              <UTextarea
                v-model="definition"
                :rows="20"
                class="w-full font-mono"
                :readonly="selected?.status === 'published'"
                spellcheck="false"
              />
            </UFormField>
            <div class="flex flex-wrap gap-2">
              <UButton
                label="Create draft version"
                variant="outline"
                :disabled="busy || service.versions.some(v => v.status === 'draft')"
                @click="createVersion"
              /><UButton
                v-if="selected?.status === 'draft'"
                label="Save definition"
                :disabled="busy"
                @click="saveVersion"
              /><UButton
                v-if="selected?.status === 'draft'"
                label="Publish version"
                color="warning"
                :disabled="busy"
                @click="publish"
              />
            </div>
          </div>
        </UCard>
        <UCard>
          <template #header>
            <h2 class="font-semibold">
              Try the published service
            </h2>
          </template>
          <div class="space-y-4">
            <p class="text-sm text-muted">
              Validation and quotes use the current published version. A new application is pinned to that version.
            </p>
            <ApplicationDataEditor
              v-if="service.published"
              v-model="payload"
              :definition="service.published.definition"
              :errors="fieldErrors"
              :disabled="busy"
            />
            <p
              v-else
              class="text-sm text-muted"
            >
              Publish a service version to fill in an application form.
            </p>
            <div class="flex flex-wrap gap-2">
              <UButton
                label="Validate"
                variant="outline"
                :disabled="busy || !service.published"
                @click="check('validate')"
              /><UButton
                label="Get fee quote"
                variant="outline"
                :disabled="busy || !service.published"
                @click="check('quote')"
              /><UButton
                label="Create application draft"
                :disabled="busy || !service.published"
                @click="createApplication"
              />
            </div>
            <div
              v-if="validation"
              role="status"
              class="space-y-2 rounded-lg bg-elevated p-4"
            >
              <p class="font-medium">
                {{ validation.valid ? 'Payload is valid' : 'Payload needs attention' }} · v{{ validation.version }}
              </p><p
                v-for="(item, index) in validation.errors"
                :key="index"
                class="text-sm text-error"
              >
                {{ item.path || '/' }}: {{ item.message }}
              </p>
            </div>
            <FeeSummary
              v-if="quote"
              :fees="quote.fees"
            />
            <p
              v-if="busy"
              role="status"
              class="text-sm text-muted"
            >
              Working…
            </p>
          </div>
        </UCard>
      </div>
    </template>
  </div>
</template>
