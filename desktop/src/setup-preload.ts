/** Bridge for the bundled first-run page only. Never attached to remote content. */
import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('bardSetup', {
  current: (): Promise<string | null> => ipcRenderer.invoke('setup:get'),
  save: (url: string): Promise<{ ok: boolean; message?: string }> =>
    ipcRenderer.invoke('setup:save', url),
});
