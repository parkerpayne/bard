<script setup lang="ts">
/**
 * The lyre from the app icon, redrawn as strokes on a 24×24 grid so it stays
 * legible at 20px in the rail and at 56px on the login card. The geometry is
 * traced off the icon bitmap: arms sweeping down into a bowl, each curling up
 * and outward into a horn at the top, a yoke across them, and four strings.
 */
withDefaults(defineProps<{ size?: number | string }>(), { size: 22 });
</script>

<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    focusable="false"
  >
    <path
      d="M8.5 6.6C7.7 9.6 6.4 12.4 6.5 15.3 6.6 17.9 8.9 19.2 12 19.2s5.4-1.3 5.5-3.9c.1-2.9-1.2-5.7-2-8.7"
      stroke-width="2.1"
    />
    <path d="M8.5 6.6C8.2 5.6 7.8 4.9 6.8 4.6M15.5 6.6c.3-1 .7-1.7 1.7-2" stroke-width="2.1" />
    <path d="M7.9 5.85h8.2" stroke-width="1.2" />
    <path d="M9.5 6.9v10.3M11.1 6.9v10.3M12.9 6.9v10.3M14.5 6.9v10.3" stroke-width="0.85" />
  </svg>
</template>
