<script setup lang="ts">
import { useApi } from '~/shared/composables/useApi'
import type { ApplicationSummary } from '~/shared/types/api'
import ApiFeedback from '~/shared/components/ApiFeedback.vue'

const route = useRoute()
const api = useApi()
const page = computed(() => {
  const value = Number(route.query.page)
  return Number.isInteger(value) && value > 0 && value <= 100000 ? value : 1
})
const serviceCode = computed(() => typeof route.query.serviceCode === 'string' ? route.query.serviceCode : '')
const statusFilter = computed(() => typeof route.query.status === 'string' ? route.query.status : '')
const filters = reactive({ serviceCode: serviceCode.value, status: statusFilter.value })
watch([serviceCode, statusFilter], () => {
  filters.serviceCode = serviceCode.value
  filters.status = statusFilter.value
})
const { data, status, error, refresh } = await useAsyncData('applications', () => {
  const params = new URLSearchParams({ page: String(page.value), pageSize: '12' })
  if (serviceCode.value) params.set('serviceCode', serviceCode.value)
  if (statusFilter.value) params.set('status', statusFilter.value)
  return api<ApplicationSummary[]>(`/v1/applications?${params}`)
}, { watch: [page, serviceCode, statusFilter] })
function applyFilters() {
  return navigateTo({ path: '/applications', query: {
    ...(filters.serviceCode.trim() ? { serviceCode: filters.serviceCode.trim() } : {}),
    ...(filters.status ? { status: filters.status } : {})
  } })
}
function changePage(value: number) {
  return navigateTo({ path: '/applications', query: { ...route.query, page: value } })
}
</script>

<template>
  <UCard>
    <template #header>
      <div class="flex items-center justify-between gap-4">
        <h2 class="font-semibold">
          Recent applications
        </h2>
        <UButton
          label="Refresh"
          icon="i-lucide-refresh-cw"
          variant="outline"
          :loading="status === 'pending'"
          @click="refresh()"
        />
      </div>
    </template>
    <form
      class="mb-6 flex flex-wrap items-end gap-3"
      @submit.prevent="applyFilters"
    >
      <UFormField label="Service code">
        <UInput
          v-model="filters.serviceCode"
          placeholder="All services"
          maxlength="64"
        />
      </UFormField>
      <UFormField label="Status">
        <USelect
          v-model="filters.status"
          :items="[{ label: 'All statuses', value: '' }, { label: 'Draft', value: 'draft' }, { label: 'Submitted', value: 'submitted' }]"
          class="w-40"
        />
      </UFormField>
      <UButton
        type="submit"
        label="Apply filters"
        :disabled="status === 'pending'"
      />
      <UButton
        to="/applications"
        label="Clear filters"
        variant="ghost"
      />
    </form>
    <ApiFeedback :error="error" />
    <p
      v-if="status === 'pending'"
      role="status"
    >
      Loading applications…
    </p>
    <div
      v-else-if="!error && data?.data.length"
      class="overflow-x-auto"
    >
      <table class="w-full text-left text-sm">
        <caption class="sr-only">
          Applications, newest first
        </caption>
        <thead class="border-b border-default text-muted">
          <tr>
            <th
              scope="col"
              class="p-3"
            >
              Application
            </th>
            <th
              scope="col"
              class="p-3"
            >
              Service
            </th>
            <th
              scope="col"
              class="p-3"
            >
              Status
            </th>
            <th
              scope="col"
              class="p-3"
            >
              Updated
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="application in data.data"
            :key="application.id"
            class="border-b border-default"
          >
            <td class="p-3">
              <NuxtLink
                :to="{ path: '/applications', query: { ...route.query, id: application.id } }"
                class="font-mono text-xs text-primary underline"
              >{{ application.id }}</NuxtLink>
            </td>
            <td class="whitespace-nowrap p-3">
              {{ application.serviceCode }} · v{{ application.serviceVersion }}
            </td>
            <td class="p-3">
              <UBadge :color="application.status === 'submitted' ? 'success' : 'neutral'">
                {{ application.status }}
              </UBadge>
            </td>
            <td class="whitespace-nowrap p-3">
              {{ new Date(application.updatedAt).toISOString().slice(0, 16).replace('T', ' ') }} UTC
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p
      v-else-if="!error"
      class="py-8 text-center text-muted"
    >
      No applications match these filters. Create a draft from a published service in the catalog.
    </p>
    <div
      v-if="!error && data?.pagination && status !== 'pending'"
      class="mt-6 flex flex-wrap items-center justify-between gap-4"
    >
      <p class="text-sm text-muted">
        {{ data.pagination.total }} applications · Page {{ page }} of {{ Math.max(1, data.pagination.totalPages) }}
      </p>
      <div class="flex gap-2">
        <UButton
          label="Previous"
          variant="outline"
          :disabled="page <= 1"
          @click="changePage(page - 1)"
        />
        <UButton
          label="Next"
          variant="outline"
          :disabled="page >= data.pagination.totalPages"
          @click="changePage(page + 1)"
        />
      </div>
    </div>
  </UCard>
</template>
