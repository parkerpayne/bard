/**
 * The login page's entry point.
 *
 * Deliberately no PrimeVue and no primeicons: this bundle is inlined into one
 * self-contained HTML file, so every kilobyte here is a kilobyte a signed-out
 * visitor downloads before they can type a password. The page needs two form
 * controls, and Login.vue styles those itself off the same CSS variables the
 * app uses.
 */
import { createApp } from 'vue';

import Login from './Login.vue';
import './styles.css';

createApp(Login).mount('#app');
