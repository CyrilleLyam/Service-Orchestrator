<script setup lang="ts">
import { parseObject, useApi } from '#layers/shared/app/composables/useApi'
import type { Application, ApplicationDetail } from '#layers/shared/app/types/api'
import ApiFeedback from '#layers/shared/app/components/ApiFeedback.vue'
import FeeSummary from '#layers/shared/app/components/FeeSummary.vue'

const api = useApi()
const route = useRoute()
const id = ref(typeof route.query.id === 'string' ? route.query.id : '')
const application = ref<ApplicationDetail | null>(null)
const patch = ref('{}')
const busy = ref(false)
const error = shallowRef<unknown>(null)
const notice = ref('')
const endpoint = () => `/v1/applications/${encodeURIComponent(application.value?.id ?? id.value.trim())}`
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
async function reload() {
  application.value = (await api<ApplicationDetail>(endpoint())).data
}
function load() {
  return run(async () => {
    application.value = null
    if (!/^[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}$/i.test(id.value.trim())) throw new Error('Enter a valid application UUID.')
    await reload()
    patch.value = '{}'
    await navigateTo({ path: '/applications', query: { id: application.value!.id } }, { replace: true })
  })
}
function save() {
  return run(async () => {
    await api<Application>(endpoint(), { method: 'PATCH', body: { data: parseObject(patch.value) }, headers: { 'Content-Type': 'application/merge-patch+json' } })
    await reload()
    patch.value = '{}'
    notice.value = 'Draft changes saved.'
  })
}
function submit() {
  return run(async () => {
    if (Object.keys(parseObject(patch.value)).length) throw new Error('Save or clear the pending patch before submitting.')
    await api<Application>(`${endpoint()}/submit`, { method: 'POST' })
    await reload()
    notice.value = 'Application submitted. Its data and fee snapshot are now locked.'
  })
}
onMounted(() => {
  if (id.value) load()
})
watch(() => route.query.id, (value) => {
  if (typeof value === 'string' && value !== application.value?.id) {
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
        Resume a draft or inspect a submitted application by its ID.
      </p>
    </div>
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
      Create an application from a published service in the catalog. The backend retrieves applications by ID and does not provide an application list.
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
              Saved application data
            </h2>
          </template>
          <pre class="overflow-auto rounded-lg bg-elevated p-4 text-sm">{{ JSON.stringify(application.data, null, 2) }}</pre>
          <div
            v-if="application.status === 'draft'"
            class="mt-5 space-y-4"
          >
            <UFormField
              label="Draft changes (JSON Merge Patch)"
              description="Only changed fields are needed. Set a field to null to remove it; nested objects merge."
            >
              <UTextarea
                v-model="patch"
                :rows="8"
                class="w-full font-mono"
                spellcheck="false"
              />
            </UFormField>
            <div class="flex flex-wrap gap-2">
              <UButton
                label="Save draft changes"
                variant="outline"
                :disabled="busy"
                @click="save"
              /><UButton
                label="Submit application"
                :disabled="busy"
                @click="submit"
              />
            </div>
            <p class="text-xs text-muted">
              Submission validates and calculates fees using the pinned service version. Successful submission locks this application.
            </p>
          </div>
        </UCard>
        <div class="space-y-6">
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
