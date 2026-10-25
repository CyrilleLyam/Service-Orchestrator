<script setup lang="ts">
import ServiceWorkspace from '~/features/catalog/components/ServiceWorkspace.vue'

const route = useRoute()
</script>

<template>
  <ServiceWorkspace
    :key="String(route.params.code)"
    :code="String(route.params.code)"
    @application-created="navigateTo(`/applications?id=${$event}`)"
  />
</template>
