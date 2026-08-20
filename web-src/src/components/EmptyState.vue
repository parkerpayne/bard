<script setup lang="ts">
defineProps<{ title: string; hint?: string; icon?: string }>();
</script>

<template>
  <div class="empty">
    <i :class="icon || 'pi pi-inbox'" />
    <h3>{{ title }}</h3>
    <p v-if="hint">{{ hint }}</p>
    <slot />
  </div>
</template>

<style scoped>
.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 56px 16px;
  text-align: center;
  color: var(--fg-muted);
}

.empty i {
  font-size: 30px;
  color: var(--fg-dim);
  margin-bottom: 6px;
}

.empty h3 {
  font-size: 17px;
  font-weight: 700;
  color: var(--fg);
}

.empty p {
  font-size: 13px;
  max-width: 34ch;
}
</style>
