<script setup lang="ts">
import { ApiError } from '~/shared/composables/useApi'

const props = defineProps<{ error: unknown }>()
const detail = computed(() => props.error instanceof ApiError ? props.error.detail : null)
const message = computed(() => props.error instanceof Error ? props.error.message : 'The request could not be completed.')
</script>

<template>
  <div
    v-if="error"
    role="alert"
    class="rounded-xl border border-error/30 bg-error/5 p-4 text-sm"
  >
    <p class="font-semibold text-error">
      {{ message }}
    </p>
    <ul
      v-if="detail?.errors.length"
      class="mt-2 space-y-1"
    >
      <li
        v-for="(item, index) in detail.errors"
        :key="index"
      >
        {{ item.path || '/' }}: {{ item.message }}
      </li>
    </ul>
    <p
      v-if="detail?.requestId"
      class="mt-2 text-xs text-muted"
    >
      Request ID: {{ detail.requestId }}
    </p>
  </div>
</template>
