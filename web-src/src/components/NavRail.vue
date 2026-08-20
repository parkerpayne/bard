<script setup lang="ts">
/**
 * The side rail on a desktop and the bottom tab bar on a phone — one set of
 * items, two layouts, so the active tab never has to be tracked twice.
 */
import { api } from '@/lib/api';
import { currentRoute, showTab, type TabName } from '@/lib/router';
import BardMark from './BardMark.vue';

const tabs: { id: TabName; label: string; icon: string }[] = [
  { id: 'playlists', label: 'Playlists', icon: 'pi pi-list' },
  { id: 'library', label: 'Library', icon: 'pi pi-database' },
  { id: 'settings', label: 'Settings', icon: 'pi pi-cog' },
];

async function signOut() {
  await api.logout();
  location.replace('/login');
}
</script>

<template>
  <nav class="rail">
    <div class="brand">
      <BardMark :size="21" />
      <span>Bard Music</span>
    </div>

    <button
      v-for="tab in tabs"
      :key="tab.id"
      class="item"
      :class="{ active: currentRoute.tab === tab.id }"
      :aria-current="currentRoute.tab === tab.id ? 'page' : undefined"
      @click="showTab(tab.id)"
    >
      <i :class="tab.icon" />
      <span>{{ tab.label }}</span>
    </button>

    <button class="item signout" @click="signOut">
      <i class="pi pi-sign-out" />
      <span>Sign out</span>
    </button>
  </nav>
</template>

<style scoped>
.rail {
  grid-area: rail;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 20px 10px 12px;
  background: var(--ink-050);
  border-right: 1px solid var(--line);
  overflow-y: auto;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 8px 18px;
  font-size: 15px;
  font-weight: 720;
  letter-spacing: -0.2px;
  user-select: none;
}

.brand :deep(svg) {
  color: var(--accent);
}

.item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 9px 12px;
  border: none;
  border-radius: 8px;
  background: none;
  color: var(--fg-muted);
  font-size: 13px;
  font-weight: 640;
  cursor: pointer;
  text-align: left;
  transition: color 0.12s, background 0.12s;
}

.item i {
  font-size: 16px;
}

.item:hover {
  color: var(--fg);
}

.item.active {
  color: var(--fg);
  background: rgba(255, 255, 255, 0.07);
}

.signout {
  margin-top: auto;
}

@media (max-width: 760px) {
  .rail {
    flex-direction: row;
    gap: 0;
    padding: 0 0 env(safe-area-inset-bottom);
    border-right: none;
    border-top: 1px solid var(--line);
    overflow: visible;
  }

  .brand {
    display: none;
  }

  .item {
    flex: 1;
    flex-direction: column;
    justify-content: center;
    gap: 3px;
    padding: 8px 4px;
    border-radius: 0;
    font-size: 10px;
    text-align: center;
  }

  .item.active {
    background: none;
    color: var(--accent);
  }

  .signout {
    margin-top: 0;
  }
}
</style>
