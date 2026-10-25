<script setup lang="ts">
import type { Fees } from '~/shared/types/api'

defineProps<{ fees: Fees }>()
</script>

<template>
  <section
    class="space-y-3 rounded-xl bg-elevated p-5"
    aria-label="Fee breakdown"
  >
    <h3 class="font-semibold">
      Fee breakdown
    </h3>
    <div
      v-for="item in fees.items"
      :key="item.code"
      class="flex justify-between gap-4 text-sm"
    >
      <span>{{ typeof item.label === 'string' ? item.label : item.label?.en || item.code }}</span>
      <span>{{ item.amount.toLocaleString() }} minor units</span>
    </div>
    <div class="flex justify-between border-t border-default pt-3 font-semibold">
      <span>Total · {{ fees.currency || 'No currency' }}</span><span>{{ fees.total.toLocaleString() }} minor units</span>
    </div>
    <p class="text-xs text-muted">
      Amounts are shown in the currency's minor units, as returned by the API.
    </p>
  </section>
</template>
