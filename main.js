const { app, BrowserWindow, ipcMain, shell, dialog } = require('electron');
const path = require('path');
const { exec } = require('child_process');

function createWindow() {
  const mainWindow = new BrowserWindow({
    width: 400,
    height: 400,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    resizable: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  // Load the index.html of the app.
  mainWindow.loadFile('index.html');

  // Make the window ignore mouse events where the background is transparent
  // We can let the user click on the 3D character or UI elements
  // This depends on how we structure the UI, for now we will keep it simple.
}

app.whenReady().then(() => {
  createWindow();

  app.on('activate', function () {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', function () {
  if (process.platform !== 'darwin') app.quit();
});

// Setup IPC handlers for system actions
ipcMain.handle('open-url', async (event, url) => {
  try {
    await shell.openExternal(url);
    return { success: true, message: `Opened URL: ${url}` };
  } catch (error) {
    return { success: false, message: `Failed to open URL: ${error.message}` };
  }
});

ipcMain.handle('generate-content', async (event, apiKey, prompt, systemInstruction) => {
  try {
    const response = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=${apiKey}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        system_instruction: {
            parts: [{ text: systemInstruction }]
        },
        contents: [{
          parts: [{ text: prompt }]
        }]
      })
    });

    if (!response.ok) {
        return { success: false, message: `API error: ${response.status}` };
    }

    const data = await response.json();
    return { success: true, data: data };
  } catch (error) {
    return { success: false, message: `Network error: ${error.message}` };
  }
});

ipcMain.handle('execute-command', async (event, command) => {
  return new Promise(async (resolve) => {
    const { response } = await dialog.showMessageBox({
      type: 'warning',
      buttons: ['Yes', 'No'],
      defaultId: 1,
      title: 'Command Execution Warning',
      message: `The AI wants to execute the following command on your system:\n\n${command}\n\nDo you want to allow this?`,
    });

    if (response === 0) {
      exec(command, (error, stdout, stderr) => {
        if (error) {
          resolve({ success: false, message: `Command failed: ${error.message}` });
          return;
        }
        resolve({ success: true, message: `Command executed successfully. Output: ${stdout}` });
      });
    } else {
      resolve({ success: false, message: 'Command execution cancelled by user.' });
    }
  });
});
