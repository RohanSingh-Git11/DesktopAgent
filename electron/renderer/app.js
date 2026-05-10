const { ipcRenderer } = require('electron');

const taskInput = document.getElementById('task-input');
const runBtn = document.getElementById('run-btn');
const stepsList = document.getElementById('steps-list');
const logs = document.getElementById('logs');
const confidenceBar = document.getElementById('confidence-bar');
const confidenceVal = document.getElementById('confidence-val');
const activeAppVal = document.getElementById('active-app-val');
const settingsBtn = document.getElementById('settings-btn');
const settingsModal = document.getElementById('settings-modal');
const saveSettingsBtn = document.getElementById('save-settings');

// State
let currentTaskSteps = [];

// Listen for backend messages
ipcRenderer.on('backend-msg', (event, msg) => {
    addLog(`[${msg.type}]`);

    switch(msg.type) {
        case 'agent_plan_generated':
            renderPlan(msg.steps);
            break;
        case 'agent_step_update':
            updateStep(msg.index, msg.status, msg.all_steps);
            break;
        case 'agent_state_update':
            updateState(msg);
            break;
        case 'agent_observation':
            if (msg.type === 'browser' || msg.type === 'desktop') {
                addLog(`Ref Map Received (${msg.type})`);
                renderObservation(msg.snapshot);
            }
            break;
        case 'system_info':
            addLog(`SYS: ${msg.message}`);
            break;
        case 'agent_task_finished':
            addLog('Task complete: ' + (msg.result.success ? 'SUCCESS' : 'FAILED'));
            document.getElementById('status-text').innerText = 'SYSTEM READY';
            break;
        case 'error':
            addLog('ERROR: ' + msg.message);
            break;
    }
});

function addLog(text) {
    const entry = document.createElement('div');
    entry.className = 'log-entry';
    entry.innerText = `[${new Date().toLocaleTimeString()}] ${text}`;
    logs.appendChild(entry);
    logs.scrollTop = logs.scrollHeight;
}

function renderPlan(steps) {
    stepsList.innerHTML = '';
    currentTaskSteps = steps;
    steps.forEach((step, i) => {
        const div = document.createElement('div');
        div.className = 'step-item';
        div.id = `step-${i}`;
        div.innerHTML = `<span class="step-idx">${i+1}.</span> ${step.description}`;
        stepsList.appendChild(div);
    });
}

function renderObservation(snapshot) {
    // Add to logs in a formatted way
    const entry = document.createElement('div');
    entry.className = 'log-entry observation';
    entry.style.color = '#00f2ff';
    entry.style.borderLeft = '1px solid #00f2ff';
    entry.style.paddingLeft = '5px';
    entry.style.marginTop = '5px';
    entry.innerText = `OBSERVATION REFS:\n${snapshot}`;
    logs.appendChild(entry);
}

function updateStep(index, status, all_steps) {
    const el = document.getElementById(`step-${index}`);
    if (el) {
        el.className = `step-item ${status}`;
    }
}

function updateState(state) {
    if (state.confidence !== undefined) {
        const percent = Math.round(state.confidence * 100);
        confidenceBar.style.width = `${percent}%`;
        confidenceVal.innerText = `${percent}%`;
    }
    if (state.active_app) {
        activeAppVal.innerText = state.active_app.toUpperCase();
    }
}

runBtn.addEventListener('click', () => {
    const prompt = taskInput.value.trim();
    if (prompt) {
        ipcRenderer.send('send-to-backend', {
            type: 'agent_task',
            prompt: prompt,
            request_id: 'task-' + Date.now()
        });
        addLog(`Initiating task: ${prompt}`);
        document.getElementById('status-text').innerText = 'EXECUTING';
        taskInput.value = '';

        const behavior = document.getElementById('ui-behavior').value;
        if (behavior === 'minimized') {
            ipcRenderer.send('minimize-app');
        }
    }
});

settingsBtn.addEventListener('click', () => {
    settingsModal.style.display = 'flex';
});

saveSettingsBtn.addEventListener('click', () => {
    const apiKey = document.getElementById('api-key-input').value;
    if (apiKey) {
        ipcRenderer.send('send-to-backend', {
            type: 'agent_settings',
            settings: { api_key: apiKey }
        });
    }
    settingsModal.style.display = 'none';
});

// Window controls
document.getElementById('close-btn').addEventListener('click', () => ipcRenderer.send('close-app'));
document.getElementById('minimize-btn').addEventListener('click', () => ipcRenderer.send('minimize-app'));
