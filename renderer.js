import * as THREE from 'three';
// The import maps strategy might fail in electron depending on the bundler / environment.
// Since we have nodeIntegration: false, we cannot use require directly, but module loading
// via relative paths should work if we import from node_modules.

// For genai, since it's a server-side/client-side SDK, we can import it through a bundled
// script or dynamically. We'll use the REST API directly to avoid complex bundling issues in
// vanilla JS renderer without a bundler like Webpack/Vite.

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

const renderer = new THREE.WebGLRenderer({ alpha: false, antialias: true });
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setClearColor(0x222222, 1); // Solid background matching body
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
    await processInput(transcript);
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
  const text = textInput.value.trim();
  if (text) {
    textInput.value = '';
    statusDiv.textContent = `You typed: "${text}"`;
    await processInput(text);
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


// --- Basic Rule-Based Action Parsing ---

async function processInput(prompt) {
  const text = prompt.toLowerCase();

  if (text.includes("open google")) {
      const msg = "Opening Google.";
      statusDiv.textContent = msg;
      await speak(msg);
      if (window.electronAPI) {
          await window.electronAPI.openUrl("https://www.google.com");
      }
  } else if (text.includes("open calculator") || text.includes("open calc")) {
      const msg = "Opening calculator.";
      statusDiv.textContent = msg;
      await speak(msg);
      if (window.electronAPI) {
          await window.electronAPI.executeCommand("calc");
      }
  } else if (text.includes("open notepad")) {
      const msg = "Opening notepad.";
      statusDiv.textContent = msg;
      await speak(msg);
      if (window.electronAPI) {
          await window.electronAPI.executeCommand("notepad");
      }
  } else {
      const defaultResponse = "I'm just a simple voice assistant without AI now. I can only open Google, Calculator, or Notepad.";
      statusDiv.textContent = defaultResponse;
      await speak(defaultResponse);
  }
}

// Pre-load voices
if (window.speechSynthesis) {
  window.speechSynthesis.onvoiceschanged = () => {
    window.speechSynthesis.getVoices();
  };
}
