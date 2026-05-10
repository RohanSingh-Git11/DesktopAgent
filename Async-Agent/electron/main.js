const { app, BrowserWindow, globalShortcut, ipcMain } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

let mainWindow;
let backendProcess;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 900,
    height: 700,
    frame: false,
    transparent: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    },
    alwaysOnTop: true,
    skipTaskbar: true
  });

  mainWindow.loadFile('electron/renderer/index.html');
  mainWindow.center();

  // Handle hotkey visibility - Windows + J (Super+J)
  globalShortcut.register('Super+J', () => {
    if (mainWindow.isVisible()) {
      mainWindow.hide();
    } else {
      mainWindow.show();
      mainWindow.focus();
    }
  });

  // Fallback for non-Super platforms or reserved keys
  globalShortcut.register('CommandOrControl+J', () => {
    if (mainWindow.isVisible()) {
      mainWindow.hide();
    } else {
      mainWindow.show();
      mainWindow.focus();
    }
  });
}

function startBackend() {
  let backendPath;
  if (app.isPackaged) {
    backendPath = path.join(process.resourcesPath, 'backend', 'async_backend', 'async_backend.exe');
    if (process.platform !== 'win32') {
       backendPath = path.join(process.resourcesPath, 'backend', 'async_backend', 'async_backend');
    }
    backendProcess = spawn(backendPath);
  } else {
    const pythonCmd = process.platform === 'win32' ? 'python' : 'python3';
    backendProcess = spawn(pythonCmd, ['desktop_backend.py']);
  }

  backendProcess.stdout.on('data', (data) => {
    try {
      const msg = JSON.parse(data.toString());
      mainWindow.webContents.send('backend-msg', msg);
    } catch (e) {
      console.log('Backend raw:', data.toString());
    }
  });

  backendProcess.stderr.on('data', (data) => {
    console.error('Backend Error:', data.toString());
  });
}

app.whenReady().then(() => {
  createWindow();
  startBackend();

  app.on('activate', function () {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', function () {
  if (process.platform !== 'darwin') app.quit();
});

ipcMain.on('send-to-backend', (event, arg) => {
  if (backendProcess) {
    backendProcess.stdin.write(JSON.stringify(arg) + '\n');
  }
});

ipcMain.on('minimize-app', () => {
  mainWindow.minimize();
});

ipcMain.on('close-app', () => {
  app.quit();
});
