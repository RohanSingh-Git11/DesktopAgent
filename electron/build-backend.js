const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

console.log('--- Packaging Python Backend ---');

const buildDir = path.join(__dirname, '..', 'build', 'backend');
if (!fs.existsSync(buildDir)) {
    fs.mkdirSync(buildDir, { recursive: true });
}

try {
    console.log('Installing pyinstaller...');
    execSync('pip install pyinstaller', { stdio: 'inherit' });

    console.log('Running pyinstaller...');
    // We bundle the backend into a single folder in build/backend
    execSync(`pyinstaller --noconfirm --onedir --windowed --name async_backend --add-data "python${path.delimiter}python" --distpath "${buildDir}" desktop_backend.py`, { stdio: 'inherit' });

    console.log('Backend bundled successfully.');
} catch (error) {
    console.error('Error bundling backend:', error.message);
    process.exit(1);
}
