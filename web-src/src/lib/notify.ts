/**
 * A thin seam between plain modules and PrimeVue's Toast service, which is only
 * injectable inside a component. App.vue registers the real notifier at mount;
 * until then messages are dropped rather than thrown.
 */
export interface NotifyMessage {
  severity: 'success' | 'info' | 'error';
  summary: string;
  detail?: string;
  life?: number;
}

type Notifier = (message: NotifyMessage) => void;

let notifier: Notifier = () => {};

export function setNotifier(fn: Notifier): void {
  notifier = fn;
}

export const notify = {
  success(summary: string, detail?: string) {
    notifier({ severity: 'success', summary, detail, life: 2600 });
  },
  info(summary: string, detail?: string) {
    notifier({ severity: 'info', summary, detail, life: 2600 });
  },
  error(summary: string, detail?: string) {
    notifier({ severity: 'error', summary, detail, life: 4200 });
  },
};
