<script setup lang="ts">
/**
 * The one page a signed-out visitor can reach. It is built as a single
 * self-contained file (see vite.login.config.ts), so it must not reach for
 * anything under /assets — that path is behind the session cookie this page
 * exists to hand out.
 */
import { onMounted, ref, useTemplateRef } from 'vue';
import BardMark from '@/components/BardMark.vue';

const username = ref('');
const password = ref('');
const error = ref('');
const busy = ref(false);
const userField = useTemplateRef<HTMLInputElement>('userField');

/** Only same-origin paths are honoured, matching the server's own check. */
const raw = new URLSearchParams(location.search).get('next') ?? '/';
const next = raw.startsWith('/') && !raw.startsWith('//') ? raw : '/';

onMounted(() => userField.value?.focus());

async function submit() {
  if (busy.value) return;
  busy.value = true;
  error.value = '';

  try {
    const response = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: username.value.trim(), password: password.value, next }),
    });
    const data = (await response.json().catch(() => ({}))) as {
      ok?: boolean;
      redirect?: string;
      message?: string;
    };
    if (response.ok && data.ok) {
      location.replace(data.redirect || next);
      return;
    }
    error.value = data.message || `Sign-in failed (HTTP ${response.status})`;
  } catch {
    error.value = 'Network error — is the bot running?';
  }

  password.value = '';
  busy.value = false;
}
</script>

<template>
  <form class="card" autocomplete="on" @submit.prevent="submit">
    <div class="brand">
      <BardMark :size="30" />
      <span>Bard Music</span>
    </div>
    <p class="sub">Sign in to continue</p>

    <label for="username">Username</label>
    <input
      id="username"
      ref="userField"
      v-model="username"
      name="username"
      type="text"
      autocomplete="username"
      autocapitalize="none"
      autocorrect="off"
      spellcheck="false"
      required
    />

    <label for="password">Password</label>
    <input
      id="password"
      v-model="password"
      name="password"
      type="password"
      autocomplete="current-password"
      required
    />

    <button type="submit" :disabled="busy">{{ busy ? 'Signing in…' : 'Sign in' }}</button>
    <p class="error">{{ error }}</p>
  </form>
</template>

<style scoped>
.card {
  width: 100%;
  max-width: 360px;
  padding: 32px 28px;
  border: 1px solid var(--line);
  border-radius: 16px;
  background: var(--ink-100);
  box-shadow: var(--shadow-lift);
}

.brand {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  font-size: 18px;
  font-weight: 720;
  letter-spacing: -0.3px;
}

.brand :deep(svg) {
  color: var(--accent);
}

.sub {
  text-align: center;
  color: var(--fg-muted);
  font-size: 13px;
  margin: 6px 0 26px;
}

label {
  display: block;
  font-size: 12px;
  font-weight: 640;
  color: var(--fg-muted);
  margin-bottom: 6px;
}

input {
  width: 100%;
  padding: 11px 12px;
  margin-bottom: 16px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.05);
  outline: none;
  transition: border-color 0.12s, background 0.12s;
}

input:focus {
  border-color: var(--accent);
  background: rgba(255, 255, 255, 0.07);
}

button {
  width: 100%;
  margin-top: 4px;
  padding: 12px;
  border: none;
  border-radius: 999px;
  background: var(--accent);
  color: #000;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.12s, transform 0.08s;
}

button:hover:not(:disabled) {
  background: var(--accent-hi);
}

button:active:not(:disabled) {
  transform: scale(0.985);
}

button:disabled {
  opacity: 0.6;
  cursor: default;
}

.error {
  min-height: 18px;
  margin-top: 14px;
  text-align: center;
  font-size: 12.5px;
  color: var(--danger);
}
</style>
