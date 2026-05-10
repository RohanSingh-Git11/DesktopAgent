// Use the exposed API from preload.js
const { electronAPI } = window;

const taskInput = document.getElementById('task-input');
const runBtn = document.getElementById('run-btn');
const stepsList = document.getElementById('steps-list');
const skillsList = document.getElementById('skills-list');
const logs = document.getElementById('logs');
const confidenceBar = document.getElementById('confidence-bar');
const confidenceVal = document.getElementById('confidence-val');
const activeAppVal = document.getElementById('active-app-val');
const settingsBtn = document.getElementById('settings-btn');
const settingsModal = document.getElementById('settings-modal');
const saveSettingsBtn = document.getElementById('save-settings');
const tabBtns = document.querySelectorAll('.tab-btn');
const tabViews = document.querySelectorAll('.tab-view');

// State
let currentTaskSteps = [];

// Listen for backend messages
electronAPI.on('backend-msg', (msg) => {
    // addLog(`[${msg.type}]`);

    switch(msg.type) {
        case 'agent_plan_generated':
            renderPlan(msg.steps);
            switchToTab('plan');
            break;
        case 'agent_step_update':
            updateStep(msg.index, msg.status, msg.all_steps);
            break;
        case 'agent_state_update':
            updateState(msg);
            break;
        case 'agent_observation':
            if (msg.type === 'browser' || msg.type === 'desktop') {
                renderObservation(msg.snapshot);
            }
            break;
        case 'skills_list':
            renderSkills(msg.skills);
            break;
        case 'system_info':
            addLog(`SYS: ${msg.message}`);
            break;
        case 'agent_task_finished':
            addLog('Task complete: ' + (msg.result.success ? 'SUCCESS' : 'FAILED'));
            document.getElementById('status-text').innerText = 'SYSTEM READY';
            // Request fresh skills list
            electronAPI.send('send-to-backend', { type: 'get_skills' });
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

function renderSkills(skills) {
    skillsList.innerHTML = '';
    if (skills.length === 0) {
        skillsList.innerHTML = '<div class="empty-state">No skills learned yet</div>';
        return;
    }
    skills.forEach(skill => {
        const div = document.createElement('div');
        div.className = 'skill-item';
        div.innerHTML = `
            <h4>${skill.name}</h4>
            <p>${skill.description}</p>
            <div style="font-size: 0.6rem; color: #555; margin-top: 5px;">Uses: ${skill.success_count}</div>
        `;
        div.onclick = () => {
            taskInput.value = skill.name;
        };
        skillsList.appendChild(div);
    });
}

function renderObservation(snapshot) {
    const entry = document.createElement('div');
    entry.className = 'log-entry observation';
    entry.innerText = `OBSERVATION REFS:\n${snapshot}`;
    logs.appendChild(entry);
    logs.scrollTop = logs.scrollHeight;
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

function switchToTab(tabId) {
    tabBtns.forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tabId);
    });
    tabViews.forEach(view => {
        view.classList.toggle('active', view.id === `${tabId}-view`);
    });
}

tabBtns.forEach(btn => {
    btn.onclick = () => {
        switchToTab(btn.dataset.tab);
        if (btn.dataset.tab === 'skills') {
            electronAPI.send('send-to-backend', { type: 'get_skills' });
        }
    };
});

runBtn.addEventListener('click', () => {
    const prompt = taskInput.value.trim();
    if (prompt) {
        electronAPI.send('send-to-backend', {
            type: 'agent_task',
            prompt: prompt,
            request_id: 'task-' + Date.now()
        });
        addLog(`Initiating task: ${prompt}`);
        document.getElementById('status-text').innerText = 'EXECUTING';
        taskInput.value = '';

        const behavior = document.getElementById('ui-behavior').value;
        if (behavior === 'minimized') {
            electronAPI.send('minimize-app');
        }
    }
});

settingsBtn.addEventListener('click', () => {
    settingsModal.style.display = 'flex';
});

saveSettingsBtn.addEventListener('click', () => {
    const apiKey = document.getElementById('api-key-input').value;
    const humanMode = document.getElementById('human-mode-toggle').checked;

    const settings = {};
    if (apiKey) settings.api_key = apiKey;
    settings.human_mode = humanMode;

    electronAPI.send('send-to-backend', {
        type: 'agent_settings',
        settings: settings
    });

    settingsModal.style.display = 'none';
});

document.getElementById('add-job-btn').onclick = () => {
    const goal = prompt("Enter task for background scheduler:");
    const interval = prompt("Enter interval in seconds:", "3600");
    if (goal && interval) {
        electronAPI.send('send-to-backend', {
            type: 'add_schedule',
            goal: goal,
            interval: parseInt(interval)
        });
        addLog(`Added schedule: ${goal}`);
    }
};

// Window controls
document.getElementById('close-btn').addEventListener('click', () => electronAPI.send('close-app'));
document.getElementById('minimize-btn').addEventListener('click', () => electronAPI.send('minimize-app'));

// Initial skill fetch
electronAPI.send('send-to-backend', { type: 'get_skills' });
