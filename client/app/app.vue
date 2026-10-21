<script setup lang="ts">
useHead({ htmlAttrs: { lang: 'en' } })
useSeoMeta({ title: 'Service Orchestrator', description: 'Configure services and manage applications.' })
</script>

<template>
  <UApp>
    <UHeader>
      <template #left>
        <NuxtLink
          to="/"
          class="flex items-center gap-3 font-semibold"
        >
          <UIcon
            name="i-lucide-workflow"
            class="size-7 text-primary"
          />
          Service Orchestrator
        </NuxtLink>
      </template>
      <template #right>
        <UButton
          to="/"
          label="Services"
          variant="ghost"
          color="neutral"
        />
        <UButton
          to="/applications"
          label="Applications"
          variant="ghost"
          color="neutral"
        />
        <UColorModeButton />
      </template>
    </UHeader>
    <UMain>
      <UContainer class="py-10">
        <NuxtPage />
      </UContainer>
    </UMain>
    <UFooter>
      <p class="text-sm text-muted">
        Service Orchestrator · Define. Publish. Process.
      </p>
    </UFooter>
  </UApp>
</template>
