const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  openUrl: (url) => ipcRenderer.invoke('open-url', url),
  executeCommand: (command) => ipcRenderer.invoke('execute-command', command),
  generateContent: (apiKey, prompt, systemInstruction) => ipcRenderer.invoke('generate-content', apiKey, prompt, systemInstruction)
});
