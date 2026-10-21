<script setup lang="ts">
import { useApi } from '#layers/shared/app/composables/useApi'
import type { Service, ServiceSummary } from '#layers/shared/app/types/api'
import ApiFeedback from '#layers/shared/app/components/ApiFeedback.vue'

const api = useApi()
const page = ref(1)
const { data, status, error, refresh } = await useAsyncData('services', () => api<ServiceSummary[]>(`/v1/services?page=${page.value}&pageSize=12`), { watch: [page] })
const form = reactive({ code: '', name: '', description: '' })
const saving = ref(false)
const createError = shallowRef<unknown>(null)
async function create() {
  saving.value = true
  createError.value = null
  try {
    const result = await api<Service>('/v1/services', { method: 'POST', body: { ...form } })
    await navigateTo(`/services/${encodeURIComponent(result.data.code)}`)
  } catch (e) {
    createError.value = e
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="space-y-8">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <p class="text-sm font-medium text-primary">
          WORKSPACE
        </p><h1 class="mt-2 text-3xl font-bold">
          Service catalog
        </h1><p class="mt-2 text-muted">
          Define a service once. Publish it when it is ready.
        </p>
      </div>
      <UButton
        label="Refresh"
        icon="i-lucide-refresh-cw"
        variant="outline"
        :loading="status === 'pending'"
        @click="refresh()"
      />
    </div>
    <ApiFeedback :error="error" />
    <p
      v-if="status === 'pending'"
      role="status"
    >
      Loading services…
    </p>
    <div
      v-else-if="data?.data.length"
      class="grid gap-4 md:grid-cols-2 xl:grid-cols-3"
    >
      <NuxtLink
        v-for="service in data.data"
        :key="service.code"
        :to="`/services/${encodeURIComponent(service.code)}`"
        class="rounded-xl border border-default p-6 transition hover:border-primary"
      >
        <div class="flex items-center justify-between gap-2"><UIcon
          name="i-lucide-box"
          class="size-6 text-primary"
        /><UBadge
          :color="service.currentVersion ? 'primary' : 'neutral'"
          variant="subtle"
        >{{ service.currentVersion ? `Published · v${service.currentVersion}` : 'Unpublished' }}</UBadge></div>
        <h2 class="mt-5 text-lg font-semibold">{{ service.name }}</h2><p class="mt-1 text-xs text-muted">{{ service.code }}</p><p class="mt-3 text-sm text-muted">{{ service.description || 'No description yet.' }}</p>
      </NuxtLink>
    </div>
    <p
      v-else-if="!error"
      class="rounded-xl border border-dashed border-default p-8 text-center text-muted"
    >
      No services yet. Create your first service below.
    </p>
    <div
      v-if="data?.pagination"
      class="flex items-center justify-between gap-4"
    >
      <p class="text-sm text-muted">
        {{ data.pagination.total }} services · Page {{ page }} of {{ Math.max(1, data.pagination.totalPages) }}
      </p>
      <div class="flex gap-2">
        <UButton
          label="Previous"
          variant="outline"
          :disabled="page <= 1 || status === 'pending'"
          @click="page--"
        /><UButton
          label="Next"
          variant="outline"
          :disabled="page >= data.pagination.totalPages || status === 'pending'"
          @click="page++"
        />
      </div>
    </div>
    <UCard>
      <template #header>
        <h2 class="font-semibold">
          Create a service
        </h2>
      </template>
      <form
        class="space-y-4"
        @submit.prevent="create"
      >
        <div class="grid gap-4 md:grid-cols-2">
          <UFormField
            label="Service code"
            required
          >
            <UInput
              v-model="form.code"
              required
              minlength="2"
              maxlength="64"
              placeholder="parcel-delivery"
              class="w-full"
            />
          </UFormField><UFormField
            label="Name"
            required
          >
            <UInput
              v-model="form.name"
              required
              maxlength="200"
              placeholder="Parcel Delivery"
              class="w-full"
            />
          </UFormField>
        </div>
        <UFormField label="Description">
          <UTextarea
            v-model="form.description"
            maxlength="2000"
            class="w-full"
          />
        </UFormField>
        <ApiFeedback :error="createError" /><UButton
          type="submit"
          label="Create service"
          :loading="saving"
        />
      </form>
    </UCard>
  </div>
</template>
