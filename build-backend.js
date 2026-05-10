const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const rootDir = path.resolve(__dirname, "..");
const pythonCmd = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");
const buildDir = path.join(rootDir, "build");
const backendDist = path.join(buildDir, "backend");
const pyinstallerWork = path.join(buildDir, "pyinstaller");

function runStep(args, extraEnv = {}) {
  const result = spawnSync(pythonCmd, args, {
    cwd: rootDir,
    stdio: "inherit",
    env: {
      ...process.env,
      ...extraEnv
    }
  });

  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

fs.rmSync(backendDist, { recursive: true, force: true });
fs.mkdirSync(backendDist, { recursive: true });
fs.mkdirSync(pyinstallerWork, { recursive: true });

runStep(
  ["-m", "playwright", "install", "chromium"],
  { PLAYWRIGHT_BROWSERS_PATH: "0" }
);

const args = [
  "-m",
  "PyInstaller",
  "--noconfirm",
  "--clean",
  "--onefile",
  "--name",
  "thinking-surface-backend",
  "--collect-data",
  "playwright",
  "--collect-submodules",
  "scraper",
  "--hidden-import",
  "pypdf",
  "--hidden-import",
  "playwright.async_api",
  "--exclude-module",
  "easyocr",
  "--exclude-module",
  "cv2",
  "--exclude-module",
  "numpy",
  "--exclude-module",
  "torch",
  "--exclude-module",
  "torchvision",
  "--distpath",
  backendDist,
  "--workpath",
  pyinstallerWork,
  "--specpath",
  pyinstallerWork,
  "desktop_backend.py"
];

runStep(args, { PLAYWRIGHT_BROWSERS_PATH: "0" });

const exeName = process.platform === "win32" ? "thinking-surface-backend.exe" : "thinking-surface-backend";
const artifactPath = path.join(backendDist, exeName);

if (!fs.existsSync(artifactPath)) {
  console.error(`Expected backend artifact was not created: ${artifactPath}`);
  process.exit(1);
}

console.log(`Backend build ready: ${artifactPath}`);
