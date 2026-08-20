<script setup lang="ts">
/**
 * Captures one key combination by listening rather than by parsing text — the
 * user presses the shortcut they want and sees exactly what was caught.
 *
 * Emits Electron accelerator syntax ("Control+Alt+1"), because that string
 * goes to globalShortcut unchanged.
 */
import { computed, nextTick, ref, useTemplateRef } from 'vue';
import Button from 'primevue/button';

const props = defineProps<{ modelValue: string | null; disabled?: boolean }>();
const emit = defineEmits<{ save: [accelerator: string]; clear: [] }>();

const field = useTemplateRef<HTMLElement>('field');
const listening = ref(false);
const captured = ref<string | null>(null);
const hint = ref('');

/** Codes that are only ever modifiers; a combination cannot end on one. */
const MODIFIER_KEYS = new Set([
  'Control', 'Alt', 'Shift', 'Meta', 'AltGraph', 'OS', 'CapsLock',
]);

/** DOM event.key -> the name Electron wants. */
function electronKey(event: KeyboardEvent): string | null {
  const key = event.key;
  if (MODIFIER_KEYS.has(key)) return null;
  if (key === ' ') return 'Space';
  if (key === 'Escape') return 'Escape';
  if (key === '+') return 'Plus';
  // Letters and digits are the common case; Electron wants uppercase letters.
  if (/^[a-z]$/.test(key)) return key.toUpperCase();
  if (/^[0-9]$/.test(key)) return key;
  if (/^F([1-9]|1[0-9]|2[0-4])$/.test(key)) return key;
  const named: Record<string, string> = {
    ArrowUp: 'Up', ArrowDown: 'Down', ArrowLeft: 'Left', ArrowRight: 'Right',
    Enter: 'Return', Tab: 'Tab', Backspace: 'Backspace', Delete: 'Delete',
    Home: 'Home', End: 'End', PageUp: 'PageUp', PageDown: 'PageDown',
    Insert: 'Insert',
  };
  if (named[key]) return named[key];
  // Punctuation and anything else printable: pass it through as typed.
  return key.length === 1 ? key.toUpperCase() : null;
}

function onKeydown(event: KeyboardEvent) {
  event.preventDefault();
  event.stopPropagation();

  if (event.key === 'Escape') {
    stop();
    return;
  }

  const key = electronKey(event);
  if (!key) {
    hint.value = 'Keep holding — now press a letter, number or function key.';
    return;
  }

  const modifiers: string[] = [];
  if (event.ctrlKey) modifiers.push('Control');
  if (event.altKey) modifiers.push('Alt');
  if (event.shiftKey) modifiers.push('Shift');
  if (event.metaKey) modifiers.push('Super');

  if (!modifiers.length) {
    // A bare key would be swallowed system-wide, in every application.
    hint.value = 'Add Ctrl, Alt, Shift or Super — a bare key would be captured everywhere.';
    return;
  }

  captured.value = [...modifiers, key].join('+');
  hint.value = '';
}

function start() {
  if (props.disabled) return;
  listening.value = true;
  captured.value = null;
  hint.value = 'Press the combination you want. Esc cancels.';
  // The capture box only receives keys while focused, so focus it as soon as
  // it exists rather than asking the user to click it.
  void nextTick(() => field.value?.focus());
}

function stop() {
  listening.value = false;
  captured.value = null;
  hint.value = '';
}

function save() {
  if (!captured.value) return;
  emit('save', captured.value);
  stop();
}

const shown = computed(() => captured.value ?? props.modelValue);
/** Rendered as separate keycaps rather than one run-together string. */
const keys = computed(() => (shown.value ? shown.value.split('+') : []));
</script>

<template>
  <div class="recorder">
    <div
      v-if="listening"
      ref="field"
      class="capture"
      tabindex="0"
      role="textbox"
      aria-label="Press a key combination"
      @keydown="onKeydown"
      @blur="stop"
    >
      <template v-if="keys.length">
        <kbd v-for="k in keys" :key="k">{{ k }}</kbd>
      </template>
      <span v-else class="waiting">Listening…</span>
    </div>

    <div v-else class="current">
      <template v-if="keys.length">
        <kbd v-for="k in keys" :key="k">{{ k }}</kbd>
      </template>
      <span v-else class="none">Not set</span>
    </div>

    <div class="buttons">
      <template v-if="listening">
        <Button label="Save" size="small" :disabled="!captured" @click="save" />
        <Button label="Cancel" size="small" severity="secondary" variant="text" @mousedown.prevent="stop" />
      </template>
      <template v-else>
        <Button
          :label="modelValue ? 'Change' : 'Set'"
          size="small"
          severity="secondary"
          variant="outlined"
          :disabled="disabled"
          @click="start"
        />
        <Button
          v-if="modelValue"
          icon="pi pi-times"
          size="small"
          severity="danger"
          variant="text"
          rounded
          aria-label="Clear shortcut"
          v-tooltip.top="'Clear shortcut'"
          :disabled="disabled"
          @click="emit('clear')"
        />
      </template>
    </div>

    <p v-if="hint" class="hint">{{ hint }}</p>
  </div>
</template>

<style scoped>
.recorder {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.capture,
.current {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 148px;
  min-height: 32px;
  padding: 4px 8px;
  border: 1px solid var(--line-strong);
  border-radius: 8px;
}

.capture {
  border-color: var(--accent);
  outline: none;
}

kbd {
  padding: 2px 7px;
  border: 1px solid var(--line-strong);
  border-bottom-width: 2px;
  border-radius: 5px;
  background: rgba(255, 255, 255, 0.07);
  font-family: inherit;
  font-size: 11.5px;
  font-weight: 640;
  line-height: 1.5;
}

.none,
.waiting {
  font-size: 12px;
  color: var(--fg-dim);
}

.waiting {
  color: var(--accent);
}

.buttons {
  display: flex;
  align-items: center;
  gap: 4px;
}

.hint {
  flex-basis: 100%;
  font-size: 11.5px;
  color: var(--fg-muted);
}
</style>
