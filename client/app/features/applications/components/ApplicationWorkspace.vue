<script setup lang="ts">
import { ApiError, parseObject, useApi } from '~/shared/composables/useApi'
import type { Application, ApplicationDetail, Quote, Validation, Version } from '~/shared/types/api'
import { mergePatch, sameValue } from '~/shared/utils/schemaForm'
import ApiFeedback from '~/shared/components/ApiFeedback.vue'
import FeeSummary from '~/shared/components/FeeSummary.vue'
import ApplicationDataEditor from '~/shared/components/ApplicationDataEditor.vue'
import ApplicationList from '~/features/applications/components/ApplicationList.vue'

const api = useApi()
const route = useRoute()
const id = ref(typeof route.query.id === 'string' ? route.query.id : '')
const application = ref<ApplicationDetail | null>(null)
const version = ref<Version | null>(null)
const draft = ref('{}')
const busy = ref(false)
const error = shallowRef<unknown>(null)
const definitionError = shallowRef<unknown>(null)
const notice = ref('')
const validation = ref<Validation | null>(null)
const quote = ref<Quote | null>(null)
const fieldErrors = computed(() => error.value instanceof ApiError ? error.value.detail.errors : validation.value?.errors ?? [])
const dirty = computed(() => {
  if (!application.value) return false
  try {
    return !sameValue(parseObject(draft.value), application.value.data)
  } catch {
    return true
  }
})
let loadSequence = 0
const endpoint = () => `/v1/applications/${encodeURIComponent(application.value?.id ?? id.value.trim())}`
async function run(action: () => Promise<void>) {
  if (busy.value) return
  const sequence = loadSequence
  busy.value = true
  error.value = null
  notice.value = ''
  try {
    await action()
  } catch (e) {
    if (sequence === loadSequence) error.value = e
  } finally {
    if (sequence === loadSequence) busy.value = false
  }
}
async function reload() {
  const sequence = loadSequence
  const result = (await api<ApplicationDetail>(endpoint())).data
  if (sequence !== loadSequence) return
  application.value = result
  draft.value = JSON.stringify(result.data, null, 2)
}
async function load() {
  const sequence = ++loadSequence
  const requestedId = id.value.trim()
  busy.value = true
  error.value = null
  definitionError.value = null
  application.value = null
  version.value = null
  validation.value = null
  quote.value = null
  notice.value = ''
  try {
    if (!/^[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}$/i.test(requestedId)) throw new Error('Enter a valid application UUID.')
    const result = (await api<ApplicationDetail>(`/v1/applications/${encodeURIComponent(requestedId)}`)).data
    if (sequence !== loadSequence) return
    application.value = result
    draft.value = JSON.stringify(result.data, null, 2)
    if (route.query.id !== result.id) await navigateTo({ path: '/applications', query: { ...route.query, id: result.id } }, { replace: true })
    if (sequence !== loadSequence) return
    try {
      const pinned = (await api<Version>(`/v1/services/${encodeURIComponent(result.serviceCode)}/versions/${result.serviceVersion}`)).data
      if (sequence === loadSequence) version.value = pinned
    } catch (e) {
      if (sequence === loadSequence) definitionError.value = e
    }
  } catch (e) {
    if (sequence === loadSequence) error.value = e
  } finally {
    if (sequence === loadSequence) busy.value = false
  }
}
function save() {
  return run(async () => {
    if (!application.value) return
    const sequence = loadSequence
    const patch = mergePatch(application.value.data, parseObject(draft.value))
    await api<Application>(endpoint(), { method: 'PATCH', body: { data: patch }, headers: { 'Content-Type': 'application/merge-patch+json' } })
    if (sequence !== loadSequence) return
    await reload()
    if (sequence === loadSequence) notice.value = 'Draft changes saved.'
  })
}
function check(kind: 'validate' | 'quote') {
  return run(async () => {
    validation.value = null
    quote.value = null
    const sequence = loadSequence
    const body = { data: parseObject(draft.value) }
    if (kind === 'validate') {
      const result = (await api<Validation>(`${endpoint()}/validate`, { method: 'POST', body })).data
      if (sequence === loadSequence) validation.value = result
    } else {
      const result = (await api<Quote>(`${endpoint()}/quote`, { method: 'POST', body })).data
      if (sequence === loadSequence) quote.value = result
    }
  })
}
function submit() {
  return run(async () => {
    if (dirty.value) throw new Error('Save or discard your changes before submitting.')
    const sequence = loadSequence
    await api<Application>(`${endpoint()}/submit`, { method: 'POST' })
    if (sequence !== loadSequence) return
    await reload()
    if (sequence !== loadSequence) return
    quote.value = null
    validation.value = null
    notice.value = 'Application submitted. Its data and fee snapshot are now locked.'
  })
}
function discard() {
  if (application.value) draft.value = JSON.stringify(application.value.data, null, 2)
}
watch(draft, () => {
  validation.value = null
  quote.value = null
  error.value = null
  notice.value = ''
})
onBeforeUnmount(() => {
  loadSequence++
})
onMounted(() => {
  if (id.value) load()
})
watch(() => route.query.id, (value) => {
  if (typeof value !== 'string') {
    loadSequence++
    busy.value = false
    application.value = null
    version.value = null
    id.value = ''
    draft.value = '{}'
    error.value = null
    definitionError.value = null
    validation.value = null
    quote.value = null
    notice.value = ''
  } else if (value !== application.value?.id) {
    id.value = value
    load()
  }
})
</script>

<template>
  <div class="space-y-6">
    <div>
      <p class="text-sm font-medium text-primary">
        PROCESSING
      </p><h1 class="mt-2 text-3xl font-bold">
        Applications
      </h1><p class="mt-2 text-muted">
        Browse applications, resume a draft, or inspect a submitted application.
      </p>
    </div>
    <UButton
      v-if="route.query.id"
      :to="{ path: '/applications', query: { ...route.query, id: undefined } }"
      label="Back to applications"
      icon="i-lucide-arrow-left"
      variant="link"
    />
    <ApplicationList v-else />
    <form
      class="flex flex-wrap items-end gap-3"
      @submit.prevent="load"
    >
      <UFormField
        label="Application ID"
        class="min-w-64 flex-1"
      >
        <UInput
          v-model="id"
          required
          class="w-full"
          placeholder="Paste an application UUID"
        />
      </UFormField><UButton
        type="submit"
        label="Load application"
        :loading="busy"
      />
    </form>
    <ApiFeedback :error="error" /><p
      v-if="notice"
      role="status"
      class="text-sm text-success"
    >
      {{ notice }}
    </p>
    <p
      v-if="!application && !busy"
      class="text-sm text-muted"
    >
      You can also open an application directly by its ID.
    </p>
    <template v-if="application">
      <UCard>
        <div class="flex flex-wrap items-start justify-between gap-4">
          <div>
            <NuxtLink
              :to="`/services/${encodeURIComponent(application.serviceCode)}`"
              class="font-semibold text-primary"
            >{{ application.serviceCode }} · v{{ application.serviceVersion }}</NuxtLink><p class="mt-2 break-all font-mono text-xs text-muted">
              {{ application.id }}
            </p>
          </div><UBadge :color="application.status === 'submitted' ? 'success' : 'neutral'">
            {{ application.status }}
          </UBadge>
        </div>
        <p class="mt-4 text-sm text-muted">
          Updated {{ new Date(application.updatedAt).toLocaleString() }}
        </p>
      </UCard>
      <div class="grid items-start gap-6 lg:grid-cols-2">
        <UCard>
          <template #header>
            <h2 class="font-semibold">
              Application data
            </h2>
          </template>
          <pre
            v-if="application.status !== 'draft'"
            class="overflow-auto rounded-lg bg-elevated p-4 text-sm"
          >{{ JSON.stringify(application.data, null, 2) }}</pre>
          <div
            v-else
            class="space-y-4"
          >
            <p class="text-sm text-muted">
              This form and its previews use the pinned service version {{ application.serviceVersion }}. Previews include your unsaved answers.
            </p>
            <ApiFeedback :error="definitionError" />
            <ApplicationDataEditor
              v-model="draft"
              :definition="version?.definition ?? {}"
              :errors="fieldErrors"
              :disabled="busy"
            />
            <p
              v-if="dirty"
              role="status"
              class="text-sm text-warning"
            >
              You have unsaved changes.
            </p>
            <div class="flex flex-wrap gap-2">
              <UButton
                label="Save draft changes"
                variant="outline"
                :disabled="busy || !dirty"
                @click="save"
              />
              <UButton
                label="Discard changes"
                variant="ghost"
                :disabled="busy || !dirty"
                @click="discard"
              />
              <UButton
                label="Validate"
                variant="outline"
                :disabled="busy"
                @click="check('validate')"
              />
              <UButton
                label="Get fee quote"
                variant="outline"
                :disabled="busy"
                @click="check('quote')"
              />
              <UButton
                label="Submit application"
                :disabled="busy || dirty"
                @click="submit"
              />
            </div>
            <div
              v-if="validation"
              role="status"
              class="space-y-2 rounded-lg bg-elevated p-4"
            >
              <p class="font-medium">
                {{ validation.valid ? 'Payload is valid' : 'Payload needs attention' }} · v{{ validation.version }}
              </p>
              <p
                v-for="(item, index) in validation.errors"
                :key="index"
                class="text-sm text-error"
              >
                {{ item.path || '/' }}: {{ item.message }}
              </p>
            </div>
            <p class="text-xs text-muted">
              Save your answers before submitting. Successful submission locks this application.
            </p>
          </div>
        </UCard>
        <div class="space-y-6">
          <div
            v-if="quote"
            class="space-y-2"
          >
            <p class="text-sm text-muted">
              Preview for pinned v{{ quote.version }}{{ dirty ? ' · Unsaved answers' : '' }}
            </p>
            <FeeSummary :fees="quote.fees" />
          </div>
          <FeeSummary
            v-if="application.fees"
            :fees="application.fees"
          />
          <UCard>
            <template #header>
              <h2 class="font-semibold">
                Audit history
              </h2>
            </template><ol class="space-y-4">
              <li
                v-for="(event, index) in application.events"
                :key="event.id ?? index"
                class="border-l-2 border-primary pl-4"
              >
                <p class="text-sm font-medium">
                  {{ event.type }}
                </p><p class="mt-1 text-xs text-muted">
                  {{ new Date(event.createdAt).toLocaleString() }}
                </p><pre class="mt-2 overflow-auto text-xs">{{ JSON.stringify(event.metadata, null, 2) }}</pre>
              </li>
            </ol>
          </UCard>
        </div>
      </div>
    </template>
  </div>
</template>
