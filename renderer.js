import * as THREE from 'three';
// The import maps strategy might fail in electron depending on the bundler / environment.
// Since we have nodeIntegration: false, we cannot use require directly, but module loading
// via relative paths should work if we import from node_modules.

// For genai, since it's a server-side/client-side SDK, we can import it through a bundled
// script or dynamically. We'll use the REST API directly to avoid complex bundling issues in
// vanilla JS renderer without a bundler like Webpack/Vite.

const apiKeyInput = document.getElementById('api-key');
const listenBtn = document.getElementById('listen-btn');
const textInput = document.getElementById('text-input');
const sendBtn = document.getElementById('send-btn');
const statusDiv = document.getElementById('status');

// --- 3D Setup ---
const container = document.getElementById('canvas-container');
const scene = new THREE.Scene();

// We need an orthographic or perspective camera
const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
camera.position.z = 5;

const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setClearColor(0x000000, 0); // Transparent background
container.appendChild(renderer.domElement);

// Add lighting
const light = new THREE.DirectionalLight(0xffffff, 1);
light.position.set(2, 2, 5);
scene.add(light);
const ambientLight = new THREE.AmbientLight(0x404040, 2);
scene.add(ambientLight);

// Create a simple procedural character (a robot)
const robot = new THREE.Group();

// Head
const headGeometry = new THREE.BoxGeometry(1, 1, 1);
const headMaterial = new THREE.MeshPhongMaterial({ color: 0x00ffcc });
const head = new THREE.Mesh(headGeometry, headMaterial);
head.position.y = 1.5;
robot.add(head);

// Eyes
const eyeGeometry = new THREE.SphereGeometry(0.15, 16, 16);
const eyeMaterial = new THREE.MeshBasicMaterial({ color: 0xffffff });
const eye1 = new THREE.Mesh(eyeGeometry, eyeMaterial);
eye1.position.set(-0.25, 1.6, 0.5);
const eye2 = new THREE.Mesh(eyeGeometry, eyeMaterial);
eye2.position.set(0.25, 1.6, 0.5);
robot.add(eye1);
robot.add(eye2);

// Body
const bodyGeometry = new THREE.CylinderGeometry(0.8, 0.8, 2, 32);
const bodyMaterial = new THREE.MeshPhongMaterial({ color: 0x00aacc });
const body = new THREE.Mesh(bodyGeometry, bodyMaterial);
robot.add(body);

scene.add(robot);

// Animation variables
let isTalking = false;
let isListening = false;
let clock = new THREE.Clock();

function animate() {
  requestAnimationFrame(animate);

  const time = clock.getElapsedTime();

  // Idle animation (floating and slight rotation)
  robot.position.y = Math.sin(time * 2) * 0.1;
  robot.rotation.y = Math.sin(time * 0.5) * 0.2;

  // Talking animation (bouncing head)
  if (isTalking) {
    head.position.y = 1.5 + Math.abs(Math.sin(time * 15)) * 0.2;
  } else {
    head.position.y = 1.5;
  }

  // Listening animation (rotating fast)
  if (isListening) {
     eyeMaterial.color.setHex(0xff0000); // Red eyes when listening
  } else {
     eyeMaterial.color.setHex(0xffffff);
  }

  renderer.render(scene, camera);
}
animate();

// Handle window resize
window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

// --- Speech Recognition ---
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;

if (SpeechRecognition) {
  recognition = new SpeechRecognition();
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.lang = 'en-US';

  recognition.onstart = () => {
    isListening = true;
    statusDiv.textContent = 'Listening...';
    listenBtn.textContent = 'Listening...';
    listenBtn.disabled = true;
  };

  recognition.onresult = async (event) => {
    const transcript = event.results[0][0].transcript;
    statusDiv.textContent = `You said: "${transcript}"`;
    await processWithGemini(transcript);
  };

  recognition.onerror = (event) => {
    statusDiv.textContent = `Speech recognition error: ${event.error}`;
    resetListenState();
  };

  recognition.onend = () => {
    resetListenState();
  };
} else {
  statusDiv.textContent = 'Speech Recognition API not supported in this environment.';
  listenBtn.disabled = true;
}

function resetListenState() {
  isListening = false;
  listenBtn.textContent = 'Listen';
  listenBtn.disabled = false;
}

listenBtn.addEventListener('click', () => {
  const apiKey = apiKeyInput.value.trim();
  if (!apiKey) {
    statusDiv.textContent = 'Please enter a Gemini API Key first.';
    return;
  }
  if (recognition) {
    try {
      recognition.start();
    } catch (e) {
      statusDiv.textContent = 'Speech recognition failed to start. Try typing.';
    }
  } else {
      statusDiv.textContent = 'Speech API not available. Try typing.';
  }
});

sendBtn.addEventListener('click', async () => {
  const apiKey = apiKeyInput.value.trim();
  if (!apiKey) {
    statusDiv.textContent = 'Please enter a Gemini API Key first.';
    return;
  }
  const text = textInput.value.trim();
  if (text) {
    textInput.value = '';
    statusDiv.textContent = `You typed: "${text}"`;
    await processWithGemini(text);
  }
});

textInput.addEventListener('keypress', (e) => {
  if (e.key === 'Enter') {
    sendBtn.click();
  }
});


// --- Text to Speech ---
function speak(text) {
  return new Promise((resolve) => {
    if (!window.speechSynthesis) {
        console.error("Speech synthesis not supported.");
        resolve();
        return;
    }

    // Stop any ongoing speech
    window.speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(text);

    // Pick a good voice
    const voices = window.speechSynthesis.getVoices();
    const preferredVoice = voices.find(v => v.name.includes('Google') || v.name.includes('Samantha') || v.lang === 'en-US');
    if (preferredVoice) {
      utterance.voice = preferredVoice;
    }

    utterance.onstart = () => {
      isTalking = true;
    };

    utterance.onend = () => {
      isTalking = false;
      resolve();
    };

    utterance.onerror = (e) => {
      console.error("Speech error", e);
      isTalking = false;
      resolve();
    };

    window.speechSynthesis.speak(utterance);
  });
}


// --- Gemini API & Action Parsing ---

// System prompt to instruct Gemini how to respond with actions
const systemInstruction = `
You are a helpful desktop assistant.
You can help the user by chatting with them, or by executing commands on their PC.
If the user asks you to open a website, reply with a JSON object in this format:
{"action": "open-url", "value": "https://www.example.com", "message": "Opening website."}

If the user asks you to open an application (e.g. calculator, notepad), reply with a JSON object to run the command:
{"action": "execute-command", "value": "calc", "message": "Opening calculator."}
(For notepad: {"action": "execute-command", "value": "notepad", "message": "Opening notepad."})
(For linux/mac, adapt commands appropriately, but assume linux for now: e.g. "gnome-calculator" or "gedit")

If it's just a normal conversation, reply with plain text.
ONLY reply with JSON if you are executing an action. Do not wrap JSON in markdown blocks like \`\`\`json.
`;

async function processWithGemini(prompt) {
  const apiKey = apiKeyInput.value.trim();
  if (!apiKey) return;

  statusDiv.textContent = 'Thinking...';

  try {
    // We use standard fetch to the Gemini REST API to avoid bundling the SDK
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
        throw new Error(`API error: ${response.status}`);
    }

    const data = await response.json();
    const replyText = data.candidates[0].content.parts[0].text.trim();

    await handleResponse(replyText);

  } catch (error) {
    statusDiv.textContent = `Gemini Error: ${error.message}`;
  }
}

async function handleResponse(text) {
  try {
    // Check if the response is JSON (an action)
    const actionData = JSON.parse(text);

    if (actionData.action === 'open-url') {
        statusDiv.textContent = actionData.message;
        await speak(actionData.message);
        if (window.electronAPI) {
            await window.electronAPI.openUrl(actionData.value);
        }
    } else if (actionData.action === 'execute-command') {
        statusDiv.textContent = actionData.message;
        await speak(actionData.message);
        if (window.electronAPI) {
            await window.electronAPI.executeCommand(actionData.value);
        }
    }
  } catch (e) {
    // Not JSON, just normal text
    statusDiv.textContent = text;
    await speak(text);
  }
}

// Pre-load voices
if (window.speechSynthesis) {
  window.speechSynthesis.onvoiceschanged = () => {
    window.speechSynthesis.getVoices();
  };
}
