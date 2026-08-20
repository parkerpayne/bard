import { createApp } from 'vue';
import PrimeVue from 'primevue/config';
import ToastService from 'primevue/toastservice';
import ConfirmationService from 'primevue/confirmationservice';
import Tooltip from 'primevue/tooltip';
import Ripple from 'primevue/ripple';

import App from './App.vue';
import { BardPreset } from './lib/theme';

import 'primeicons/primeicons.css';
import './styles.css';

const app = createApp(App);

app.use(PrimeVue, {
  ripple: true,
  theme: {
    preset: BardPreset,
    options: {
      // The app is dark-only; index.html always carries this class, so the dark
      // token block always wins and the OS setting never gets a say.
      darkModeSelector: '.bard-dark',
      cssLayer: false,
    },
  },
});
app.use(ToastService);
app.use(ConfirmationService);
app.directive('tooltip', Tooltip);
app.directive('ripple', Ripple);

app.mount('#app');
