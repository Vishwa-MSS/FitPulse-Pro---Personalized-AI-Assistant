// =============================================
// FITPULSE PRO - FIXED SCRIPT.JS
// Fixes: CORS, Calorie Counter, YouTube Thumbnails,
//        PDF Generation, Backend Connection
// =============================================

// ✅ FIX: Use relative URLs - frontend is served by Flask so no CORS issue
// When you run python app.py, open http://localhost:5000 (NOT file://)
const BACKEND_URL = window.location.origin.includes("localhost") || window.location.origin.includes("127.0.0.1")
  ? "http://localhost:5000"
  : "";  // relative URL when served from Flask

// ✅ FIX: Centralized fetch - uses relative URLs when page is served by Flask
// This completely avoids CORS because frontend + backend are same origin
function getBackendURL() {
  // If page is served by Flask (localhost:5000), use relative URLs
  const origin = window.location.origin;
  if (origin.includes("localhost:5000") || origin.includes("127.0.0.1:5000")) {
    return "";  // relative - same server, no CORS
  }
  // Fallback for direct file:// opening - redirect user
  if (window.location.protocol === "file:") {
    return "http://localhost:5000";
  }
  return origin;
}

async function apiFetch(endpoint, options = {}) {
  const baseURL = getBackendURL();
  const url = baseURL + endpoint;
  const defaults = {
    headers: {
      "Content-Type": "application/json",
      "Accept": "application/json"
    },
  };
  // Only add mode: cors for cross-origin requests
  if (baseURL !== "") {
    defaults.mode = "cors";
  }
  const merged = {
    ...defaults,
    ...options,
    headers: { ...defaults.headers, ...(options.headers || {}) }
  };
  return fetch(url, merged);
}

// DOM refs
const sendBtn = document.getElementById("send-btn");
const userInput = document.getElementById("user-input");
const chatBox = document.getElementById("chat-box");
const typingIndicator = document.getElementById("typing-indicator");
const micBtn = document.getElementById("mic-btn");
const uploadBtn = document.getElementById("upload-btn");
const imageUpload = document.getElementById("image-upload");

// User profile
let userProfile = JSON.parse(localStorage.getItem("userProfile")) || null;

// Conversation memory
let messages = JSON.parse(localStorage.getItem("messages")) || [];

// Pose Trainer Variables
let currentWorkout = null;
let selectedWorkout = null;
let workoutGuidelines = {};
let poseEstimator = null;
let camera = null;
let repCounter = 0;
let targetReps = 10;
let currentStage = null;

// Accuracy Variables
let movementHistory = [];
let elbowPositionHistory = [];
let shoulderPositionHistory = [];
let wristPositionHistory = [];
let hipPositionHistory = [];
const HISTORY_LENGTH = 10;
const MOVEMENT_THRESHOLD = 0.03;
const ANGLE_SMOOTHING_WINDOW = 5;
let angleHistory = [];
let formViolations = [];
const MAX_VIOLATIONS_BEFORE_WARNING = 3;
let validationBuffer = 0;
const VALIDATION_BUFFER_REQUIRED = 5;

// Personal Trainer Session Variables
let activeSession = null;
let currentPhaseIndex = 0;
let currentExerciseIndex = 0;
let currentSetNumber = 1;
let sessionTimer = null;
let phaseTimer = null;
let restTimer = null;
let sessionStartTime = null;
let totalRepsCompleted = 0;
let exercisesCompleted = 0;
let isPaused = false;
let sessionFromTracker = false;

// Expose functions globally
window.sendQuick = sendQuick;
window.openPoseTrainer = openPoseTrainer;
window.closePoseTrainer = closePoseTrainer;
window.selectWorkout = selectWorkout;
window.backToSelection = backToSelection;
window.startWorkout = startWorkout;
window.stopWorkout = stopWorkout;
window.switchWorkout = switchWorkout;
window.resetCounter = resetCounter;
window.clearHistory = clearHistory;
window.openCalorieCounter = openCalorieCounter;
window.openProfileModal = openProfileModal;
window.closeProfileModal = closeProfileModal;
window.openWorkoutPDFModal = openWorkoutPDFModal;
window.closePDFModal = closePDFModal;
window.generatePDF = generatePDF;
window.openPersonalTrainerSession = openPersonalTrainerSession;
window.closeTrainerSession = closeTrainerSession;
window.createTrainerSession = createTrainerSession;
window.backToSessionConfig = backToSessionConfig;
window.startTrainerSession = startTrainerSession;
window.completeCurrentSet = completeCurrentSet;
window.skipCurrentExercise = skipCurrentExercise;
window.skipRest = skipRest;
window.dismissHydration = dismissHydration;
window.pauseSession = pauseSession;
window.endSessionEarly = endSessionEarly;
window.restartSession = restartSession;
window.openFormTrackerFromSession = openFormTrackerFromSession;

// =============================================
// INIT
// =============================================
window.addEventListener("load", () => {
  if (!messages || messages.length === 0) {
    addMessage(
      "👋 Hi, I'm <b>FitBuddy Pro</b>! I'm your AI fitness coach. Tell me about your fitness goals, ask for workout plans, or start a Guided Session with me as your personal trainer!",
      "bot"
    );
  } else {
    messages.forEach(msg => {
      addMessage(msg.content, msg.role === "user" ? "user" : "bot", true);
    });
  }
  loadWorkoutGuidelines();
  loadUserProfile();
  checkBackendConnection();
});

// ✅ FIX: Backend connection check with user feedback
async function checkBackendConnection() {
  try {
    const resp = await apiFetch("/health");
    if (resp.ok) {
      console.log("✅ Backend connected successfully");
    } else {
      console.warn("⚠️ Backend returned error:", resp.status);
    }
  } catch (err) {
    console.warn("⚠️ Backend not reachable. Running in offline mode.");
    addMessage(
      "⚠️ <b>Backend not connected.</b> Make sure to:<br>1. Run <code>python app.py</code><br>2. Then open <b>http://localhost:5000</b> (not the HTML file directly!)",
      "bot"
    );
  }
}

// =============================================
// PROFILE FUNCTIONS
// =============================================
function loadUserProfile() {
  if (userProfile) {
    document.getElementById("profile-age").value = userProfile.age || "";
    document.getElementById("profile-gender").value = userProfile.gender || "";
    document.getElementById("profile-height").value = userProfile.height || "";
    document.getElementById("profile-weight").value = userProfile.weight || "";
    document.getElementById("profile-goal").value = userProfile.goal || "";
  }
}

function openProfileModal() { document.getElementById("profile-modal").style.display = "flex"; }
function closeProfileModal() { document.getElementById("profile-modal").style.display = "none"; }

document.getElementById("profile-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  userProfile = {
    age: document.getElementById("profile-age").value,
    gender: document.getElementById("profile-gender").value,
    height: document.getElementById("profile-height").value,
    weight: document.getElementById("profile-weight").value,
    goal: document.getElementById("profile-goal").value
  };
  localStorage.setItem("userProfile", JSON.stringify(userProfile));

  try {
    await apiFetch("/save-profile", {
      method: "POST",
      body: JSON.stringify({ user_id: "default_user", ...userProfile })
    });
    addMessage("✅ Profile saved! I'll now personalize all recommendations for you.", "bot");
  } catch (err) {
    console.warn("Profile saved locally only:", err);
    addMessage("✅ Profile saved locally! (Backend offline — start app.py for full features.)", "bot");
  }
  closeProfileModal();
});

// =============================================
// PDF FUNCTIONS — FIXED
// =============================================
function openWorkoutPDFModal() {
  if (!userProfile) {
    alert("⚠️ Please set up your profile first to generate a personalized workout plan!");
    openProfileModal();
    return;
  }
  document.getElementById("pdf-modal").style.display = "flex";
  document.getElementById("pdf-status").textContent = "";
}

function closePDFModal() {
  document.getElementById("pdf-modal").style.display = "none";
  document.getElementById("pdf-status").textContent = "";
  const btn = document.getElementById("generate-pdf-btn");
  if (btn) { btn.disabled = false; btn.textContent = "📥 Generate & Download PDF"; }
}

// ✅ FIX: PDF generation with proper error handling and fallback client-side PDF
async function generatePDF() {
  const planType = document.getElementById("pdf-plan-type").value;
  const statusEl = document.getElementById("pdf-status");
  const btn = document.getElementById("generate-pdf-btn");

  statusEl.textContent = "⏳ Generating your personalized workout plan...";
  statusEl.style.color = "#2563eb";
  btn.disabled = true;
  btn.textContent = "⏳ Generating...";

  try {
    const response = await apiFetch("/generate-workout-pdf", {
      method: "POST",
      body: JSON.stringify({ user_profile: userProfile, plan_type: planType })
    });

    if (!response.ok) {
      const errText = await response.text();
      throw new Error(`Server error ${response.status}: ${errText}`);
    }

    const blob = await response.blob();
    if (blob.size === 0) throw new Error("Received empty PDF file");

    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `FitPulse_Workout_Plan_${new Date().toISOString().split("T")[0]}.pdf`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);

    statusEl.textContent = "✅ PDF downloaded successfully!";
    statusEl.style.color = "#10b981";
    btn.textContent = "✅ Downloaded!";

    setTimeout(() => closePDFModal(), 2500);

  } catch (err) {
    console.error("PDF generation error:", err);
    statusEl.style.color = "#ef4444";

    // ✅ FIX: Fallback — generate basic PDF in-browser if backend fails
    if (err.message.includes("Failed to fetch") || err.message.includes("NetworkError") || err.message.includes("CORS")) {
      statusEl.textContent = "⚠️ Backend offline. Generating basic PDF locally...";
      await generateFallbackPDF(planType);
      statusEl.textContent = "✅ Basic PDF downloaded! Start backend for full AI plan.";
      statusEl.style.color = "#f59e0b";
      btn.disabled = false;
      btn.textContent = "📥 Generate & Download PDF";
    } else {
      statusEl.textContent = `❌ Error: ${err.message}. Please ensure the backend is running.`;
      btn.disabled = false;
      btn.textContent = "📥 Generate & Download PDF";
    }
  }
}

// ✅ Client-side fallback PDF generator using HTML print
function generateFallbackPDF(planType) {
  return new Promise((resolve) => {
    const name = userProfile.goal || "General Fitness";
    const today = new Date().toLocaleDateString();

    const days = [
      { day: "Monday", focus: "Push — Chest, Shoulders, Triceps", exercises: ["Bench Press 4×10", "Shoulder Press 3×12", "Push-ups 3×15", "Dips 3×10"] },
      { day: "Tuesday", focus: "Pull — Back, Biceps", exercises: ["Pull-ups 4×8", "Barbell Row 4×10", "Bicep Curls 3×12", "Deadlift 3×8"] },
      { day: "Wednesday", focus: "Leg Day", exercises: ["Squats 4×12", "Lunges 3×12 each", "Deadlift 3×10", "Calf Raises 3×20"] },
      { day: "Thursday", focus: "REST / Active Recovery", exercises: ["Light walk 20 min", "Stretching 15 min", "Foam rolling", "Hydrate well"] },
      { day: "Friday", focus: "Upper Body", exercises: ["Bench Press 3×10", "Barbell Row 3×10", "Shoulder Press 3×12", "Pull-ups 3×8"] },
      { day: "Saturday", focus: "Core & Cardio", exercises: ["Plank 3×60s", "Crunches 3×20", "Russian Twists 3×20", "20 min cardio"] },
      { day: "Sunday", focus: "REST", exercises: ["Full rest", "Light stretching", "Meal prep", "Sleep well"] },
    ];

    const rows = days.map(d => `
      <tr>
        <td style="font-weight:700;color:#1e40af;padding:10px 14px;border:1px solid #cbd5e1;">${d.day}</td>
        <td style="padding:10px 14px;border:1px solid #cbd5e1;font-weight:600;">${d.focus}</td>
        <td style="padding:10px 14px;border:1px solid #cbd5e1;">${d.exercises.join("<br/>")}</td>
      </tr>`).join("");

    const html = `
      <!DOCTYPE html><html><head><meta charset="utf-8"/>
      <style>
        body{font-family:Arial,sans-serif;padding:32px;color:#0f172a;}
        h1{color:#1e40af;text-align:center;font-size:26px;margin-bottom:4px;}
        .sub{text-align:center;color:#6b7280;margin-bottom:24px;}
        .profile-box{background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:16px;margin-bottom:24px;}
        table{width:100%;border-collapse:collapse;font-size:13px;}
        th{background:#1e40af;color:#fff;padding:10px 14px;text-align:left;border:1px solid #1e40af;}
        td{vertical-align:top;}
        tr:nth-child(even) td{background:#f8fafc;}
        .footer{margin-top:24px;text-align:center;color:#6b7280;font-size:12px;}
      </style></head><body>
      <h1>💪 FitPulse Pro — 7-Day Workout Plan</h1>
      <div class="sub">Generated on ${today} • Plan: ${planType.replace("_", " ").toUpperCase()}</div>
      <div class="profile-box">
        <strong>Your Profile:</strong> Age ${userProfile.age} • ${userProfile.gender} • ${userProfile.height}cm • ${userProfile.weight}kg • Goal: ${userProfile.goal}
      </div>
      <table>
        <thead><tr><th>Day</th><th>Focus</th><th>Exercises</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
      <div class="footer">FitPulse Pro | AI Fitness Coaching | Stay consistent, stay strong! 💪</div>
      </body></html>`;

    const blob = new Blob([html], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `FitPulse_Plan_${today.replace(/\//g, "-")}.html`;
    document.body.appendChild(a);
    a.click();
    URL.revokeObjectURL(url);
    document.body.removeChild(a);
    setTimeout(resolve, 500);
  });
}

// =============================================
// LOAD WORKOUT GUIDELINES
// =============================================
async function loadWorkoutGuidelines() {
  try {
    const resp = await apiFetch("/workout-guidelines");
    if (!resp.ok) throw new Error("Failed to load");
    const data = await resp.json();
    workoutGuidelines = data.workouts || {};
    console.log("✅ Workout guidelines loaded:", Object.keys(workoutGuidelines).length, "exercises");
  } catch (err) {
    console.warn("Could not load workout guidelines from backend:", err.message);
    // Use built-in fallback guidelines so app still works offline
    workoutGuidelines = getBuiltInGuidelines();
  }
}

// Built-in fallback guidelines (so Form Trainer works even offline)
function getBuiltInGuidelines() {
  return {
    bicep_curl: { name: "Bicep Curl", tips: ["Keep elbows close to body", "Don't swing body", "Full range of motion"], demo_video: "https://www.youtube.com/embed/ykJmrZ5v0Oo", dos_donts: { dos: ["Keep elbows pinned", "Full ROM", "Squeeze at top"], donts: ["No swinging", "No momentum", "No partial reps"] } },
    squat: { name: "Squat", tips: ["Chest up, core tight", "Push through heels", "Knees over toes"], demo_video: "https://www.youtube.com/embed/ultWZbUMPL8", dos_donts: { dos: ["Full depth", "Knees out", "Chest up"], donts: ["No caving knees", "No rising toes", "No rounding back"] } },
    pushup: { name: "Push-up", tips: ["Straight body line", "Lower chest to ground", "45° elbows"], demo_video: "https://www.youtube.com/embed/IODxDxX7oi4", dos_donts: { dos: ["Straight line", "Full depth", "Engage core"], donts: ["No sag", "No flaring", "No half-rep"] } },
    shoulder_press: { name: "Shoulder Press", tips: ["Core tight", "Press straight overhead", "Don't arch back"], demo_video: "https://www.youtube.com/embed/qEwKCR5JCog", dos_donts: { dos: ["Core engaged", "Full lockout", "Wrists straight"], donts: ["No arching", "No dropping", "No flaring"] } },
    deadlift: { name: "Deadlift", tips: ["Bar close to body", "Neutral spine", "Drive through heels"], demo_video: "https://www.youtube.com/embed/op9kVnSso6Q", dos_donts: { dos: ["Neutral spine", "Bar close", "Hip extension"], donts: ["No rounding", "No jerking", "No looking up"] } },
    plank: { name: "Plank", tips: ["Straight line body", "Engage core", "Breathe steadily"], demo_video: "https://www.youtube.com/embed/pSHjTRCQxIw", dos_donts: { dos: ["Straight line", "Engage glutes", "Breathe"], donts: ["No sag", "No raised hips", "No holding breath"] } },
    lunges: { name: "Lunges", tips: ["Knee over ankle", "Upright torso", "Push through heel"], demo_video: "https://www.youtube.com/embed/QOVaHwm-Q6U", dos_donts: { dos: ["Knee alignment", "Upright", "Heel drive"], donts: ["No knee past toes", "No leaning", "No rushing"] } },
    pull_up: { name: "Pull-up", tips: ["Full hang start", "Chin over bar", "No kipping"], demo_video: "https://www.youtube.com/embed/eGo4IYlbE5g", dos_donts: { dos: ["Full hang", "Chin over", "Controlled"], donts: ["No kipping", "No swinging", "No half-rep"] } },
    dips: { name: "Dips", tips: ["Lower to 90°", "Shoulders down", "Lean slightly forward"], demo_video: "https://www.youtube.com/embed/2z8JmcrW-As", dos_donts: { dos: ["90° bend", "Forward lean", "Full extension"], donts: ["No shrugging", "No too deep", "No flaring"] } },
    bench_press: { name: "Bench Press", tips: ["Bar to mid-chest", "Feet flat", "Maintain arch"], demo_video: "https://www.youtube.com/embed/rT7DgCr-3pg", dos_donts: { dos: ["Mid-chest", "Feet flat", "Stable"], donts: ["No bouncing", "No flaring", "No feet up"] } },
    lateral_raise: { name: "Lateral Raise", tips: ["Raise to shoulder height", "Slight elbow bend", "No swinging"], demo_video: "https://www.youtube.com/embed/3VcKaXpzqRo", dos_donts: { dos: ["Lead elbows", "Slight bend", "Controlled"], donts: ["No swinging", "No above shoulder", "No shrugging"] } },
    barbell_row: { name: "Barbell Row", tips: ["Hinge at hips", "Pull to lower chest", "Squeeze blades"], demo_video: "https://www.youtube.com/embed/FWJR5Ve8bnQ", dos_donts: { dos: ["Flat back", "Squeeze blades", "Pull to chest"], donts: ["No rounding", "No momentum", "No looking up"] } },
  };
}

// =============================================
// CALORIE COUNTER — FIXED
// =============================================
function openCalorieCounter() {
  const food = prompt("🍎 Enter a food item (e.g., '2 eggs', '1 apple', 'chicken breast 150g'):");
  if (!food || !food.trim()) return;

  typingIndicator.style.display = "block";
  chatBox.scrollTop = chatBox.scrollHeight;

  apiFetch("/calories", {
    method: "POST",
    body: JSON.stringify({ food: food.trim(), user_profile: userProfile })
  })
    .then(async (resp) => {
      if (!resp.ok) {
        const txt = await resp.text();
        throw new Error(`Server ${resp.status}: ${txt}`);
      }
      return resp.json();
    })
    .then(data => {
      typingIndicator.style.display = "none";
      const reply = data.reply || "⚠️ No calorie data returned.";
      addMessage(reply, "bot", false, reply);
    })
    .catch(err => {
      typingIndicator.style.display = "none";
      console.error("Calorie error:", err);
      // ✅ FIX: Provide useful feedback instead of generic error
      if (err.message.includes("Failed to fetch") || err.message.includes("NetworkError")) {
        addMessage(
          "⚠️ <b>Backend not connected.</b> Please start the backend server with <code>python app.py</code> to use the calorie counter.",
          "bot"
        );
      } else {
        addMessage(`⚠️ Error fetching calorie info: ${err.message}`, "bot");
      }
    });
}

// =============================================
// CHAT FUNCTIONS
// =============================================
function addMessage(content, sender, fromHistory = false, rawTextForSave = null) {
  const bubble = document.createElement("div");
  const roleClass = (sender === "user" || sender === "User") ? "user" : "bot";
  bubble.classList.add("message", roleClass);
  bubble.innerHTML = formatBotReply(content);
  chatBox.appendChild(bubble);
  chatBox.scrollTop = chatBox.scrollHeight;

  if (!fromHistory) {
    saveHistory(content, sender, rawTextForSave);
  }
}

function saveHistory(content, sender, rawTextForSave = null) {
  const stripped = rawTextForSave ? rawTextForSave : stripHtml(content);
  const role = (sender === "user" || sender === "User") ? "user" : "assistant";
  messages.push({ role, content: stripped });
  localStorage.setItem("messages", JSON.stringify(messages));
}

function stripHtml(html) {
  return html.replace(/<[^>]*>/g, "").trim();
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function boldKeywordsInHTML(html) {
  const keywords = ["Protein", "Carbs", "Exercise", "Calories", "Goal", "Steps", "Workout", "Diet", "Plan", "Reps", "Sets"];
  const container = document.createElement("div");
  container.innerHTML = html;
  const keywordRegex = new RegExp(`\\b(${keywords.join("|")})\\b`, "gi");
  function walk(node) {
    node.childNodes.forEach(child => {
      if (child.nodeType === Node.TEXT_NODE) {
        const txt = child.textContent;
        if (keywordRegex.test(txt)) {
          const replaced = txt.replace(keywordRegex, "<b>$1</b>");
          const frag = document.createRange().createContextualFragment(replaced);
          child.replaceWith(frag);
        }
      } else {
        walk(child);
      }
    });
  }
  walk(container);
  return container.innerHTML;
}

function formatBotReply(text) {
  if (!text && text !== "") return "";
  if (/<\/?(table|ul|li|img|b|strong|br)/i.test(text)) {
    let cleaned = text.replace(/\*\*/g, "").replace(/#{1,6}\s*/g, "");
    return boldKeywordsInHTML(cleaned);
  }

  let cleaned = text.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  cleaned = cleaned.replace(/\*\*/g, "").replace(/#{1,6}\s*/g, "");

  const lines = cleaned.split("\n");
  const pipeLines = lines.filter(l => /\|/.test(l));

  if (pipeLines.length >= 2) {
    const tableBlock = [];
    for (let i = 0; i < lines.length; i++) {
      if (/\|/.test(lines[i])) tableBlock.push(lines[i]);
      else if (tableBlock.length > 0) break;
    }
    if (tableBlock.length > 0) {
      let headerRow = tableBlock[0].split("|").map(s => s.trim()).filter(Boolean);
      let bodyRows = [];
      let startIdx = 1;
      if (tableBlock.length > 1 && /^\s*\|?\s*-{1,}\s*\|?/.test(tableBlock[1])) startIdx = 2;
      for (let i = startIdx; i < tableBlock.length; i++) {
        const cols = tableBlock[i].split("|").map(s => s.trim()).filter(Boolean);
        if (cols.length) bodyRows.push(cols);
      }
      let tableHTML = '<div class="table-responsive"><table>';
      tableHTML += "<thead><tr>";
      headerRow.forEach(h => tableHTML += `<th>${escapeHtml(h)}</th>`);
      tableHTML += "</tr></thead><tbody>";
      bodyRows.forEach(r => {
        tableHTML += "<tr>";
        r.forEach(cell => tableHTML += `<td>${escapeHtml(cell)}</td>`);
        tableHTML += "</tr>";
      });
      tableHTML += "</tbody></table></div>";
      const blockText = tableBlock.join("\n");
      cleaned = cleaned.replace(blockText, tableHTML);
      return boldKeywordsInHTML(cleaned);
    }
  }

  const outParts = [];
  let inList = false;
  const bulletRegex = /^(\s*[-*•]|\s*\d+\.)\s+(.*)/;
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (line === "") {
      if (inList) { outParts.push("</ul>"); inList = false; }
      outParts.push("<br/>");
      continue;
    }
    const m = line.match(bulletRegex);
    if (m) {
      if (!inList) { outParts.push("<ul>"); inList = true; }
      outParts.push(`<li>${escapeHtml(m[2])}</li>`);
    } else {
      if (inList) { outParts.push("</ul>"); inList = false; }
      outParts.push(`<p>${escapeHtml(line)}</p>`);
    }
  }
  if (inList) outParts.push("</ul>");
  return boldKeywordsInHTML(outParts.join(""));
}

async function sendMessageToBackend(userMessage, base64Image = null) {
  if (!userMessage && !base64Image) return;

  if (userMessage) addMessage(userMessage, "user", false, userMessage);
  if (base64Image) {
    const imgHtml = `<div><strong>📷 Uploaded Image</strong><br><img src="data:image/png;base64,${base64Image}" /></div>`;
    addMessage(imgHtml, "user", false, "User uploaded image");
  }

  typingIndicator.style.display = "block";
  chatBox.scrollTop = chatBox.scrollHeight;

  try {
    const resp = await apiFetch("/chat", {
      method: "POST",
      body: JSON.stringify({ messages, image: base64Image, user_profile: userProfile })
    });

    if (!resp.ok) {
      const txt = await resp.text();
      throw new Error(`Server error ${resp.status}: ${txt}`);
    }

    const data = await resp.json();
    typingIndicator.style.display = "none";

    if (data.messages) {
      messages = data.messages;
      localStorage.setItem("messages", JSON.stringify(messages));
    }

    if (data.places && Array.isArray(data.places) && data.places.length > 0) {
      const placesHtml = renderPlacesList(data.places);
      addMessage(placesHtml, "bot", false, "Places results");
    } else {
      addMessage(data.reply || "⚠️ No reply from server", "bot", false, data.reply);
    }

  } catch (err) {
    typingIndicator.style.display = "none";
    console.error("Chat error:", err);
    if (err.message.includes("Failed to fetch") || err.message.includes("NetworkError") || err.message.includes("CORS")) {
      addMessage(
        "⚠️ <b>Cannot connect to backend.</b> Please make sure the backend is running:<br><code>python app.py</code><br>Then refresh the page.",
        "bot"
      );
    } else {
      addMessage(`⚠️ Error: ${err.message}`, "bot");
    }
  }
}

function renderPlacesList(places) {
  let html = '<div class="places-list">';
  html += '<table><thead><tr><th>#</th><th>Place</th><th>Address</th><th>Rating</th><th>Map</th></tr></thead><tbody>';
  places.forEach((p, idx) => {
    const name = escapeHtml(p.name || "Unknown");
    const addr = escapeHtml(p.address || "");
    const rating = p.rating ? `${p.rating} ⭐ (${p.user_ratings_total || 0})` : "-";
    const mapsLink = p.maps_url ? `<a href="${p.maps_url}" target="_blank" rel="noopener noreferrer">📍 Open</a>` : "-";
    html += `<tr><td>${idx + 1}</td><td>${name}</td><td>${addr}</td><td>${rating}</td><td>${mapsLink}</td></tr>`;
  });
  html += '</tbody></table></div>';
  return html;
}

// Send button
sendBtn.addEventListener("click", () => {
  const text = userInput.value.trim();
  if (!text) return;
  sendMessageToBackend(text);
  userInput.value = "";
});

userInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendBtn.click();
  }
});

function sendQuick(text) {
  userInput.value = text;
  sendBtn.click();
  userInput.value = "";
}

// Mic
micBtn.addEventListener("click", () => {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    alert("Speech recognition not supported. Please use Chrome or Edge.");
    return;
  }
  const recognition = new SpeechRecognition();
  recognition.lang = "en-US";
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;

  micBtn.disabled = true;
  micBtn.textContent = "🔴";
  recognition.start();

  recognition.onresult = (event) => {
    const transcript = event.results[0][0].transcript;
    sendMessageToBackend(transcript);
  };
  recognition.onerror = (event) => {
    console.error("SpeechRecognition error", event);
    alert("Voice recognition error: " + (event.error || "unknown"));
  };
  recognition.onend = () => {
    micBtn.disabled = false;
    micBtn.textContent = "🎤";
  };
});

// Image upload
uploadBtn.addEventListener("click", () => imageUpload.click());
imageUpload.addEventListener("change", (ev) => {
  const file = ev.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    const base64Image = reader.result.split(",")[1];
    const extraText = userInput.value.trim();
    sendMessageToBackend(extraText || "Please analyze this image", base64Image);
    userInput.value = "";
  };
  reader.readAsDataURL(file);
  imageUpload.value = "";
});

function clearHistory() {
  if (!confirm("Clear chat history?")) return;
  messages = [];
  localStorage.removeItem("messages");
  chatBox.innerHTML = "";
  addMessage("👋 Hi, I'm <b>FitBuddy Pro</b>! Ready for a fresh start?", "bot");
}

// =============================================
// ✅ FIX: YOUTUBE THUMBNAIL HELPERS
// Extracts video ID and builds thumbnail + embed URLs
// =============================================
function extractYouTubeId(url) {
  if (!url) return null;
  // Handle embed URLs: https://www.youtube.com/embed/VIDEO_ID
  const embedMatch = url.match(/youtube\.com\/embed\/([^?&"'>]+)/);
  if (embedMatch) return embedMatch[1];
  // Handle watch URLs: https://www.youtube.com/watch?v=VIDEO_ID
  const watchMatch = url.match(/[?&]v=([^&"'>]+)/);
  if (watchMatch) return watchMatch[1];
  // Handle short URLs: https://youtu.be/VIDEO_ID
  const shortMatch = url.match(/youtu\.be\/([^?&"'>]+)/);
  if (shortMatch) return shortMatch[1];
  return null;
}

function setDemoVideo(embedUrl) {
  const videoId = extractYouTubeId(embedUrl);
  const thumbnail = document.getElementById("demo-thumbnail");
  const iframe = document.getElementById("demo-video");
  const playOverlay = document.getElementById("yt-play-overlay");
  const container = document.getElementById("yt-thumbnail-container");

  if (!thumbnail || !iframe) return;

  // Reset to thumbnail state
  iframe.style.display = "none";
  iframe.src = "";
  thumbnail.style.display = "block";
  if (playOverlay) playOverlay.style.display = "flex";

  if (videoId) {
    // ✅ Use multiple thumbnail quality fallbacks
    thumbnail.src = `https://img.youtube.com/vi/${videoId}/hqdefault.jpg`;
    thumbnail.onerror = function () {
      // Fallback to medium quality if HQ fails
      this.onerror = function () {
        // Final fallback: default quality
        this.onerror = null;
        this.src = `https://img.youtube.com/vi/${videoId}/default.jpg`;
      };
      this.src = `https://img.youtube.com/vi/${videoId}/mqdefault.jpg`;
    };

    // Click to play: replace thumbnail with iframe
    const playHandler = () => {
      thumbnail.style.display = "none";
      if (playOverlay) playOverlay.style.display = "none";
      iframe.src = `https://www.youtube.com/embed/${videoId}?autoplay=1&rel=0&modestbranding=1`;
      iframe.style.display = "block";
      // Remove listener after first click
      if (playOverlay) playOverlay.removeEventListener("click", playHandler);
      thumbnail.removeEventListener("click", playHandler);
    };

    if (playOverlay) playOverlay.addEventListener("click", playHandler);
    thumbnail.addEventListener("click", playHandler);

  } else {
    // No valid video ID — show a placeholder
    thumbnail.src = "https://img.icons8.com/color/200/play-button-circled.png";
    thumbnail.style.objectFit = "contain";
    thumbnail.style.padding = "20px";
    if (playOverlay) playOverlay.style.display = "none";
  }
}

// =============================================
// POSE TRAINER
// =============================================
function openPoseTrainer() {
  document.getElementById("pose-trainer-modal").style.display = "flex";
  document.getElementById("workout-selection").style.display = "block";
  document.getElementById("workout-config").style.display = "none";
  document.getElementById("camera-view").style.display = "none";
}

function closePoseTrainer() {
  stopWorkout();
  document.getElementById("pose-trainer-modal").style.display = "none";
  if (sessionFromTracker) sessionFromTracker = false;
}

function selectWorkout(workoutType) {
  selectedWorkout = workoutType;
  const workout = workoutGuidelines[workoutType];
  if (!workout) { alert("Workout not found!"); return; }

  document.getElementById("workout-selection").style.display = "none";
  document.getElementById("workout-config").style.display = "block";
  document.getElementById("config-workout-name").textContent = `Configure: ${workout.name}`;
}

function backToSelection() {
  document.getElementById("workout-config").style.display = "none";
  document.getElementById("workout-selection").style.display = "block";
  selectedWorkout = null;
}

async function startWorkout() {
  if (!selectedWorkout) return;
  currentWorkout = selectedWorkout;
  targetReps = parseInt(document.getElementById("target-reps").value) || 10;

  const workout = workoutGuidelines[currentWorkout];
  if (!workout) { alert("Workout data not found!"); return; }

  document.getElementById("workout-config").style.display = "none";
  document.getElementById("camera-view").style.display = "block";
  document.getElementById("current-workout-name").textContent = workout.name;

  // ✅ FIX: Use new setDemoVideo function for YouTube thumbnails
  setDemoVideo(workout.demo_video);

  // Tips
  const tipsList = document.getElementById("tips-list");
  tipsList.innerHTML = "";
  (workout.tips || []).forEach(tip => {
    const li = document.createElement("li");
    li.textContent = tip;
    tipsList.appendChild(li);
  });

  const dosList = document.getElementById("dos-list");
  const dontsList = document.getElementById("donts-list");
  dosList.innerHTML = "";
  dontsList.innerHTML = "";
  if (workout.dos_donts) {
    (workout.dos_donts.dos || []).forEach(item => {
      const li = document.createElement("li");
      li.textContent = item;
      dosList.appendChild(li);
    });
    (workout.dos_donts.donts || []).forEach(item => {
      const li = document.createElement("li");
      li.textContent = item;
      dontsList.appendChild(li);
    });
  }

  // Reset state
  repCounter = 0;
  currentStage = null;
  validationBuffer = 0;
  movementHistory = [];
  elbowPositionHistory = [];
  shoulderPositionHistory = [];
  wristPositionHistory = [];
  hipPositionHistory = [];
  angleHistory = [];
  formViolations = [];
  // Reset ACPF tracking
  window._acpfCurrentAngle = 0;
  window._acpfFormOk = true;
  window._acpfRepCount = 0;
  _repMinAngle = 999; _repMaxAngle = 0;
  // Clear per-exercise angle history so previous exercise doesn't contaminate
  if (typeof angleHistories !== 'undefined') {
    Object.keys(angleHistories).forEach(k => { angleHistories[k] = []; });
  }
  validationBuffer = 0;
  _repConfirmCount = 0;

  document.getElementById("rep-count").textContent = "0";
  document.getElementById("rep-target").textContent = `/ ${targetReps}`;
  document.getElementById("stage-display").textContent = "Ready";
  document.getElementById("form-display").textContent = "Get in position...";

  await initializePoseEstimation();
}

function stopWorkout() {
  if (camera) { camera.stop(); camera = null; }
  if (poseEstimator) { poseEstimator.close(); poseEstimator = null; }
  const video = document.getElementById("pose-video");
  if (video && video.srcObject) {
    video.srcObject.getTracks().forEach(t => t.stop());
    video.srcObject = null;
  }
  currentWorkout = null;
  selectedWorkout = null;
  repCounter = 0;
  currentStage = null;

  // Reset demo video
  const iframe = document.getElementById("demo-video");
  if (iframe) { iframe.src = ""; iframe.style.display = "none"; }
  const thumb = document.getElementById("demo-thumbnail");
  if (thumb) { thumb.src = ""; }
}

function switchWorkout() {
  stopWorkout();
  document.getElementById("camera-view").style.display = "none";
  document.getElementById("workout-selection").style.display = "block";
}

function resetCounter() {
  repCounter = 0;
  currentStage = null;
  validationBuffer = 0;
  movementHistory = [];
  elbowPositionHistory = [];
  shoulderPositionHistory = [];
  wristPositionHistory = [];
  hipPositionHistory = [];
  angleHistory = [];
  formViolations = [];
  document.getElementById("rep-count").textContent = "0";
  document.getElementById("stage-display").textContent = "Ready";
  document.getElementById("form-display").textContent = "Starting...";
}

// =============================================
// PERSONAL TRAINER SESSION
// =============================================
function openPersonalTrainerSession() {
  if (!userProfile) {
    alert("⚠️ Please set up your profile first to get personalized coaching!");
    openProfileModal();
    return;
  }
  document.getElementById("trainer-session-modal").style.display = "flex";
  document.getElementById("session-config-step").style.display = "block";
  document.getElementById("session-overview-step").style.display = "none";
  document.getElementById("active-session-step").style.display = "none";
  document.getElementById("session-complete-step").style.display = "none";
}

function closeTrainerSession() {
  if (sessionTimer) clearInterval(sessionTimer);
  if (phaseTimer) clearInterval(phaseTimer);
  if (restTimer) clearInterval(restTimer);

  activeSession = null;
  currentPhaseIndex = 0;
  currentExerciseIndex = 0;
  currentSetNumber = 1;
  totalRepsCompleted = 0;
  exercisesCompleted = 0;
  isPaused = false;

  document.getElementById("trainer-session-modal").style.display = "none";
}

async function createTrainerSession() {
  const sessionConfig = {
    workout_type: document.getElementById("session-workout-type").value,
    duration: document.getElementById("session-duration").value,
    include_warmup: document.getElementById("session-include-warmup").checked,
    include_cardio: document.getElementById("session-include-cardio").checked,
    include_cooldown: document.getElementById("session-include-cooldown").checked
  };

  const btn = document.querySelector(".create-session-btn");
  if (btn) { btn.disabled = true; btn.textContent = "⏳ Creating Session..."; }

  try {
    const response = await apiFetch("/create-session", {
      method: "POST",
      body: JSON.stringify({ user_profile: userProfile, session_config: sessionConfig })
    });

    if (!response.ok) throw new Error("Failed to create session");
    const data = await response.json();
    activeSession = data.session;

    displaySessionOverview();
    document.getElementById("session-config-step").style.display = "none";
    document.getElementById("session-overview-step").style.display = "block";

  } catch (err) {
    console.error("Error creating session:", err);
    alert("❌ Error creating session. Make sure the backend is running (python app.py).");
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "🚀 Create My Session"; }
  }
}

function displaySessionOverview() {
  const names = { push: "Push Day", pull: "Pull Day", leg: "Leg Day", upper: "Upper Body", lower: "Lower Body", core: "Core & Abs" };
  const wName = names[activeSession.config.workout_type] || "Workout";

  document.getElementById("session-overview-title").textContent = `🎖️ ${wName} — Personal Training Session`;
  document.getElementById("session-overview-duration").textContent = `Total Duration: ${activeSession.total_duration_formatted}`;

  const phasesList = document.getElementById("session-phases-list");
  phasesList.innerHTML = "";

  activeSession.phases.forEach((phase) => {
    const card = document.createElement("div");
    card.className = "phase-overview-card";

    let icon = "💪";
    if (phase.phase === "warmup") icon = "🔥";
    if (phase.phase === "cardio") icon = "🏃";
    if (phase.phase === "cooldown") icon = "🧘";

    let exercisesHTML = "";
    if (phase.exercises && phase.exercises.length > 0) {
      if (phase.phase === "workout" || phase.phase === "cardio") {
        exercisesHTML = phase.exercises.map(ex =>
          `<div class="exercise-item">• ${ex.name} — ${ex.sets} sets × ${ex.reps} reps</div>`
        ).join("");
      } else {
        exercisesHTML = phase.exercises.map(ex =>
          `<div class="exercise-item">• ${ex.name}${ex.duration ? ` (${ex.duration}s)` : ""}</div>`
        ).join("");
      }
    }

    card.innerHTML = `
      <div class="phase-card-header">
        <span class="phase-icon">${icon}</span>
        <div>
          <h4 style="margin:0; font-size:18px;">${phase.title}</h4>
          ${phase.duration ? `<p style="margin:4px 0 0 0; color:#6b7280; font-size:14px;">${Math.floor(phase.duration / 60)} minutes</p>` : ""}
        </div>
      </div>
      ${exercisesHTML ? `<div class="phase-exercises-list">${exercisesHTML}</div>` : ""}
    `;
    phasesList.appendChild(card);
  });
}

function backToSessionConfig() {
  document.getElementById("session-overview-step").style.display = "none";
  document.getElementById("session-config-step").style.display = "block";
}

function startTrainerSession() {
  sessionStartTime = Date.now();
  currentPhaseIndex = 0;
  currentExerciseIndex = 0;
  currentSetNumber = 1;
  totalRepsCompleted = 0;
  exercisesCompleted = 0;
  isPaused = false;

  document.getElementById("session-overview-step").style.display = "none";
  document.getElementById("active-session-step").style.display = "block";
  startPhase(0);
}

async function startPhase(phaseIndex) {
  if (phaseIndex >= activeSession.phases.length) {
    completeSession();
    return;
  }

  currentPhaseIndex = phaseIndex;
  const phase = activeSession.phases[phaseIndex];

  document.getElementById("active-phase-title").textContent = phase.title;
  const subtitle = phase.target_muscles
    ? `Target: ${phase.target_muscles.join(", ")}`
    : (phase.duration ? `Duration: ${Math.floor(phase.duration / 60)} min` : "");
  document.getElementById("active-phase-subtitle").textContent = subtitle;

  // Get coaching (non-blocking)
  try {
    const coaching = await apiFetch(`/get-coaching/${activeSession.session_id}/${phase.phase}/0`);
    const coachData = await coaching.json();
    displayCoachMessage(coachData.motivation || phase.coaching_tips[0]);
    if (coachData.hydration_reminder) {
      setTimeout(() => showHydrationReminder(), 3000);
    }
  } catch (err) {
    displayCoachMessage(phase.coaching_tips && phase.coaching_tips[0] ? phase.coaching_tips[0] : "💪 Let's go!");
  }

  if (phase.phase === "warmup" || phase.phase === "cooldown") {
    startTimedPhase(phase);
  } else {
    currentExerciseIndex = 0;
    startExercise(0);
  }

  updateSessionProgress();
}

function startTimedPhase(phase) {
  document.getElementById("current-exercise-card").style.display = "none";
  let timeRemaining = phase.duration || 300;
  const timerDisplay = document.getElementById("phase-timer-display");

  if (phaseTimer) clearInterval(phaseTimer);
  phaseTimer = setInterval(() => {
    if (isPaused) return;
    timeRemaining--;
    const mins = Math.floor(timeRemaining / 60);
    const secs = timeRemaining % 60;
    timerDisplay.textContent = `${mins}:${secs.toString().padStart(2, "0")}`;

    if (timeRemaining === Math.floor(phase.duration / 2)) displayCoachMessage("💪 Halfway there! Keep it up!");
    if (timeRemaining === 30) displayCoachMessage("⏰ 30 seconds left! Finish strong!");
    if (timeRemaining <= 0) {
      clearInterval(phaseTimer);
      displayCoachMessage("✅ Phase complete! Great work!");
      setTimeout(() => startPhase(currentPhaseIndex + 1), 2000);
    }
  }, 1000);
}

async function startExercise(exerciseIndex) {
  const phase = activeSession.phases[currentPhaseIndex];
  if (exerciseIndex >= (phase.exercises || []).length) {
    if (phaseTimer) clearInterval(phaseTimer);
    displayCoachMessage("🎉 Phase complete! Excellent work!");
    setTimeout(() => startPhase(currentPhaseIndex + 1), 3000);
    return;
  }

  currentExerciseIndex = exerciseIndex;
  currentSetNumber = 1;
  const exercise = phase.exercises[exerciseIndex];

  document.getElementById("current-exercise-card").style.display = "block";
  document.getElementById("current-exercise-name").textContent = exercise.name;
  document.getElementById("current-exercise-info").textContent = `${exercise.sets} sets × ${exercise.reps} reps`;
  document.getElementById("current-set-display").textContent = `${currentSetNumber}/${exercise.sets}`;
  document.getElementById("current-exercise-tip").textContent = (exercise.tips && exercise.tips[0]) ? exercise.tips[0] : "";

  try {
    const coaching = await apiFetch(`/get-coaching/${activeSession.session_id}/${phase.phase}/${exerciseIndex}`);
    const coachData = await coaching.json();
    displayCoachMessage(coachData.motivation || `🔥 Time for ${exercise.name}!`);
    if (coachData.hydration_reminder && exerciseIndex > 0 && exerciseIndex % 3 === 0) {
      setTimeout(() => showHydrationReminder(), 2000);
    }
  } catch (err) {
    displayCoachMessage(`🔥 Time for ${exercise.name}! Focus on form!`);
  }

  updateSessionProgress();
}

function completeCurrentSet() {
  const phase = activeSession.phases[currentPhaseIndex];
  const exercise = phase.exercises[currentExerciseIndex];
  totalRepsCompleted += parseInt(exercise.reps) || 0;

  if (currentSetNumber < exercise.sets) {
    currentSetNumber++;
    document.getElementById("current-set-display").textContent = `${currentSetNumber}/${exercise.sets}`;
    displayCoachMessage(`✅ Set complete! Rest for ${exercise.rest_between_sets || 60} seconds.`);
    startRestPeriod(exercise.rest_between_sets || 60);
  } else {
    exercisesCompleted++;
    displayCoachMessage(`🎉 ${exercise.name} complete! Moving to next...`);
    playSound("success");
    setTimeout(() => startExercise(currentExerciseIndex + 1), 2000);
  }
}

function startRestPeriod(duration) {
  document.getElementById("rest-timer-panel").style.display = "flex";
  let timeRemaining = duration;
  const restDisplay = document.getElementById("rest-timer-display");
  restDisplay.textContent = timeRemaining;

  if (restTimer) clearInterval(restTimer);
  restTimer = setInterval(() => {
    if (isPaused) return;
    timeRemaining--;
    restDisplay.textContent = timeRemaining;
    if (timeRemaining === 10) displayCoachMessage("⏰ 10 seconds! Get ready for the next set.");
    if (timeRemaining <= 0) {
      clearInterval(restTimer);
      document.getElementById("rest-timer-panel").style.display = "none";
      displayCoachMessage("💪 Rest over! Let's go!");
      playSound("goal");
    }
  }, 1000);
}

function skipRest() {
  if (restTimer) clearInterval(restTimer);
  document.getElementById("rest-timer-panel").style.display = "none";
  displayCoachMessage("💪 Skipping rest! Ready for the next set!");
}

function skipCurrentExercise() {
  if (!confirm("Skip this exercise?")) return;
  if (restTimer) clearInterval(restTimer);
  document.getElementById("rest-timer-panel").style.display = "none";
  displayCoachMessage("⏭️ Skipping exercise. Moving on...");
  setTimeout(() => startExercise(currentExerciseIndex + 1), 1500);
}

function showHydrationReminder() {
  const reminder = document.getElementById("hydration-reminder");
  if (reminder) reminder.style.display = "flex";
  setTimeout(() => { if (reminder) reminder.style.display = "none"; }, 5000);
}

function dismissHydration() {
  const reminder = document.getElementById("hydration-reminder");
  if (reminder) reminder.style.display = "none";
}

function pauseSession() {
  isPaused = !isPaused;
  const btn = document.getElementById("pause-btn");
  if (isPaused) {
    btn.innerHTML = "▶️ Resume";
    displayCoachMessage("⏸️ Session paused. Take your time!");
  } else {
    btn.innerHTML = "⏸️ Pause";
    displayCoachMessage("▶️ Resuming session. Let's keep going!");
  }
}

function endSessionEarly() {
  if (!confirm("End this session early?")) return;
  if (sessionTimer) clearInterval(sessionTimer);
  if (phaseTimer) clearInterval(phaseTimer);
  if (restTimer) clearInterval(restTimer);
  completeSession();
}

function displayCoachMessage(message) {
  const coachPanel = document.getElementById("coaching-panel");
  const coachMessage = document.getElementById("coach-message");
  if (coachMessage) coachMessage.textContent = message;
  if (coachPanel) {
    coachPanel.style.animation = "none";
    setTimeout(() => { coachPanel.style.animation = "slideIn 0.5s ease"; }, 10);
  }
}

function updateSessionProgress() {
  const totalPhases = activeSession.phases.length;
  let totalProgress = (currentPhaseIndex / totalPhases) * 100;

  const phase = activeSession.phases[currentPhaseIndex];
  if (phase && phase.exercises && phase.exercises.length > 0) {
    const exerciseProgress = currentExerciseIndex / phase.exercises.length;
    totalProgress += (exerciseProgress / totalPhases) * 100;
  }

  totalProgress = Math.min(100, Math.round(totalProgress));
  document.getElementById("progress-fill").style.width = `${totalProgress}%`;
  document.getElementById("progress-percentage").textContent = `${totalProgress}%`;
}

async function completeSession() {
  if (sessionTimer) clearInterval(sessionTimer);
  if (phaseTimer) clearInterval(phaseTimer);
  if (restTimer) clearInterval(restTimer);

  document.getElementById("active-session-step").style.display = "none";
  document.getElementById("session-complete-step").style.display = "block";

  try {
    const response = await apiFetch(`/complete-session/${activeSession.session_id}`, {
      method: "POST",
      body: JSON.stringify({ total_reps: totalRepsCompleted, exercises_completed: exercisesCompleted })
    });
    const data = await response.json();
    const summary = data.summary;

    document.getElementById("session-summary").innerHTML = `
      <div class="summary-card"><div class="summary-icon">⏱️</div><div class="summary-label">Duration</div><div class="summary-value">${summary.total_duration}</div></div>
      <div class="summary-card"><div class="summary-icon">🏋️</div><div class="summary-label">Exercises</div><div class="summary-value">${summary.exercises_completed}</div></div>
      <div class="summary-card"><div class="summary-icon">💪</div><div class="summary-label">Total Reps</div><div class="summary-value">${summary.total_reps}</div></div>
      <div class="summary-card"><div class="summary-icon">🔥</div><div class="summary-label">Phases</div><div class="summary-value">${summary.phases_completed}</div></div>
    `;
    document.getElementById("achievements-section").innerHTML = `
      <h3 style="text-align:center; margin-bottom:16px; color:#0f172a;">🏆 Achievements Unlocked</h3>
      <div class="achievements-grid">
        ${(summary.achievements || []).map(a => `<div class="achievement-badge">${a}</div>`).join("")}
      </div>
    `;
  } catch (err) {
    console.error("Error completing session:", err);
    document.getElementById("session-summary").innerHTML = `
      <div class="summary-card"><div class="summary-icon">🏋️</div><div class="summary-label">Exercises</div><div class="summary-value">${exercisesCompleted}</div></div>
      <div class="summary-card"><div class="summary-icon">💪</div><div class="summary-label">Total Reps</div><div class="summary-value">${totalRepsCompleted}</div></div>
    `;
    document.getElementById("achievements-section").innerHTML = `
      <h3 style="text-align:center; margin-bottom:16px; color:#0f172a;">🏆 Achievements</h3>
      <div class="achievements-grid"><div class="achievement-badge">⭐ Workout Completed!</div></div>
    `;
  }
  playSound("goal");
}

function restartSession() {
  closeTrainerSession();
  setTimeout(() => openPersonalTrainerSession(), 300);
}

function openFormTrackerFromSession() {
  if (!activeSession) return;
  const phase = activeSession.phases[currentPhaseIndex];
  const exercise = phase && phase.exercises ? phase.exercises[currentExerciseIndex] : null;

  if (!exercise) { alert("No exercise selected."); return; }

  let exerciseKey = null;
  for (const [key, guideline] of Object.entries(workoutGuidelines)) {
    if (guideline.name === exercise.name) { exerciseKey = key; break; }
  }

  if (!exerciseKey) { alert("Form tracking not available for this exercise yet."); return; }

  sessionFromTracker = true;
  selectedWorkout = exerciseKey;

  const workout = workoutGuidelines[exerciseKey];
  document.getElementById("pose-trainer-modal").style.display = "flex";
  document.getElementById("workout-selection").style.display = "none";
  document.getElementById("workout-config").style.display = "none";
  document.getElementById("camera-view").style.display = "block";

  currentWorkout = exerciseKey;
  targetReps = parseInt(exercise.reps) || 10;

  document.getElementById("current-workout-name").textContent = workout.name;
  setDemoVideo(workout.demo_video); // ✅ Use fixed thumbnail function

  document.getElementById("target-reps").value = targetReps;
  document.getElementById("rep-target").textContent = `/ ${targetReps}`;

  const tipsList = document.getElementById("tips-list");
  tipsList.innerHTML = "";
  (workout.tips || []).forEach(tip => {
    const li = document.createElement("li");
    li.textContent = tip;
    tipsList.appendChild(li);
  });

  const dosList = document.getElementById("dos-list");
  const dontsList = document.getElementById("donts-list");
  dosList.innerHTML = "";
  dontsList.innerHTML = "";
  if (workout.dos_donts) {
    (workout.dos_donts.dos || []).forEach(item => {
      const li = document.createElement("li"); li.textContent = item; dosList.appendChild(li);
    });
    (workout.dos_donts.donts || []).forEach(item => {
      const li = document.createElement("li"); li.textContent = item; dontsList.appendChild(li);
    });
  }

  repCounter = 0; currentStage = null; validationBuffer = 0;
  movementHistory = []; elbowPositionHistory = []; shoulderPositionHistory = [];
  wristPositionHistory = []; hipPositionHistory = []; angleHistory = []; formViolations = [];

  document.getElementById("rep-count").textContent = "0";
  document.getElementById("stage-display").textContent = "Ready";
  document.getElementById("form-display").textContent = "Get in position...";

  initializePoseEstimation();
}

// =============================================
// POSE ESTIMATION LOGIC
// =============================================
async function initializePoseEstimation() {
  const videoElement = document.getElementById("pose-video");
  const canvasElement = document.getElementById("pose-canvas");
  const canvasCtx = canvasElement.getContext("2d");

  document.getElementById("loading-overlay").style.display = "flex";

  // Check if MediaPipe is available
  if (typeof Pose === "undefined") {
    console.error("MediaPipe Pose not loaded");
    document.getElementById("loading-overlay").style.display = "none";
    document.getElementById("form-display").textContent = "MediaPipe not loaded";
    return;
  }

  poseEstimator = new Pose({
    locateFile: (file) => `https://cdn.jsdelivr.net/npm/@mediapipe/pose/${file}`
  });

  poseEstimator.setOptions({
    modelComplexity: 1,
    smoothLandmarks: true,
    enableSegmentation: false,
    smoothSegmentation: false,
    minDetectionConfidence: 0.7,
    minTrackingConfidence: 0.7
  });

  poseEstimator.onResults((results) => onPoseResults(results, canvasElement, canvasCtx));

  if (typeof Camera !== "undefined") {
    camera = new Camera(videoElement, {
      onFrame: async () => {
        if (poseEstimator) await poseEstimator.send({ image: videoElement });
      },
      width: 640,
      height: 480
    });
    camera.start();
  } else {
    // Fallback: use getUserMedia directly
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true });
      videoElement.srcObject = stream;
      videoElement.onloadedmetadata = () => {
        videoElement.play();
        const sendFrames = async () => {
          if (poseEstimator && videoElement.readyState >= 2) {
            await poseEstimator.send({ image: videoElement });
          }
          if (currentWorkout) requestAnimationFrame(sendFrames);
        };
        sendFrames();
      };
    } catch (err) {
      console.error("Camera error:", err);
      document.getElementById("form-display").textContent = "Camera access denied";
    }
  }

  setTimeout(() => {
    document.getElementById("loading-overlay").style.display = "none";
  }, 2500);
}

function onPoseResults(results, canvas, ctx) {
  canvas.width = results.image.width;
  canvas.height = results.image.height;
  ctx.save();
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  if (results.poseLandmarks) {
    if (typeof drawConnectors !== "undefined") {
      drawConnectors(ctx, results.poseLandmarks, POSE_CONNECTIONS, { color: "#00FF00", lineWidth: 4 });
      drawLandmarks(ctx, results.poseLandmarks, { color: "#FF0000", lineWidth: 2, radius: 6 });
    }
    analyzeWorkoutForm(results.poseLandmarks);

    // ACPF: store shoulder Y for real-time breathing estimation
    const _ls = results.poseLandmarks[11];
    const _rs = results.poseLandmarks[12];
    if (_ls && _rs) {
      window._lastShoulderLandmarks = {
        left_shoulder_y: _ls.y,
        right_shoulder_y: _rs.y
      };
    }
  }
  ctx.restore();
}

function analyzeWorkoutForm(landmarks) {
  if (!currentWorkout || !workoutGuidelines[currentWorkout]) return;
  const workout = workoutGuidelines[currentWorkout];
  switch (currentWorkout) {
    case "bicep_curl": analyzeBicepCurlAccurate(landmarks, workout); break;
    case "shoulder_press": analyzeShoulderPressAccurate(landmarks, workout); break;
    case "lateral_raise": analyzeLateralRaiseAccurate(landmarks, workout); break;
    case "squat": analyzeSquat(landmarks, workout); break;
    case "pushup": analyzePushup(landmarks, workout); break;
    case "deadlift": analyzeDeadlift(landmarks, workout); break;
    case "plank": analyzePlank(landmarks, workout); break;
    case "lunges": analyzeLunges(landmarks, workout); break;
    case "pull_up": analyzePullUp(landmarks, workout); break;
    case "dips": analyzeDips(landmarks, workout); break;
    case "bench_press": analyzeBenchPress(landmarks, workout); break;
    case "barbell_row": analyzeBarbellRow(landmarks, workout); break;
  }
}

// =============================================
// UTILITY FUNCTIONS
// =============================================
function calculateAngle(a, b, c) {
  const radians = Math.atan2(c.y - b.y, c.x - b.x) - Math.atan2(a.y - b.y, a.x - b.x);
  let angle = Math.abs(radians * 180.0 / Math.PI);
  if (angle > 180.0) angle = 360 - angle;
  return angle;
}

// Per-exercise angle history so switching exercises doesn't contaminate readings
const angleHistories = {};
function smoothAngleFor(exerciseName, angle) {
  if (!angleHistories[exerciseName]) angleHistories[exerciseName] = [];
  const hist = angleHistories[exerciseName];
  hist.push(angle);
  if (hist.length > ANGLE_SMOOTHING_WINDOW) hist.shift();
  return hist.reduce((a, b) => a + b, 0) / hist.length;
}
// Legacy alias (still used by older calls)
function smoothAngle(angle) {
  return smoothAngleFor(currentWorkout || 'default', angle);
}

function calculateDistance(p1, p2) {
  return Math.sqrt((p2.x - p1.x) ** 2 + (p2.y - p1.y) ** 2);
}

function isPositionStable(currentPos, historyArray, threshold = MOVEMENT_THRESHOLD) {
  historyArray.push({ x: currentPos.x, y: currentPos.y, z: currentPos.z || 0 });
  if (historyArray.length > HISTORY_LENGTH) historyArray.shift();
  if (historyArray.length < 3) return true;
  const recent = historyArray.slice(-3);
  const avgX = recent.reduce((s, p) => s + p.x, 0) / recent.length;
  const avgY = recent.reduce((s, p) => s + p.y, 0) / recent.length;
  const maxDev = Math.max(...recent.map(p => Math.sqrt((p.x - avgX) ** 2 + (p.y - avgY) ** 2)));
  return maxDev < threshold;
}

function hasSignificantMovement(currentPos, historyArray, threshold = 0.05) {
  if (historyArray.length < 2) return false;
  return calculateDistance(currentPos, historyArray[historyArray.length - 1]) > threshold;
}

// ─── Real form score for ACPF payload ────────────────────────────────────────
// Tracks actual angle range seen this rep for ROM calculation
let _repMinAngle = 999, _repMaxAngle = 0;
function updateRepAngleRange(angle) {
  if (angle < _repMinAngle) _repMinAngle = angle;
  if (angle > _repMaxAngle) _repMaxAngle = angle;
}
function getRepROM() {
  return Math.min(100, (_repMaxAngle - _repMinAngle));
}
function resetRepAngleRange() { _repMinAngle = 999; _repMaxAngle = 0; }

// =============================================
// EXERCISE ANALYSIS FUNCTIONS
// =============================================

// ─── Shared rep counter helper ────────────────────────────────────────────────
// VALIDATION_BUFFER_REQUIRED lowered from 5 to 2 — more responsive
const REP_CONFIRM_FRAMES = 2;
let _repConfirmCount = 0;

function _countRep(feedback, stageAfter, stageText) {
  repCounter++;
  window._acpfRepCount = repCounter;
  document.getElementById("rep-count").textContent = repCounter;
  playSound("success");
  checkGoalReached();
  currentStage = stageAfter;
  validationBuffer = 0;
  _repConfirmCount = 0;
  resetRepAngleRange();
  return { ok: true, feedback, stageText };
}

// ─── BICEP CURL ───────────────────────────────────────────────────────────────
// Angle: shoulder(11) - elbow(13) - wrist(15)
// DOWN (arm extended): ~160-180°   UP (arm curled): ~30-70°
function analyzeBicepCurlAccurate(landmarks, workout) {
  // Try RIGHT arm first (13,15), fall back to LEFT (14,16)
  let shoulder = landmarks[11], elbow = landmarks[13], wrist = landmarks[15];
  // Use whichever arm has better visibility (higher confidence via z)
  if (landmarks[12] && landmarks[14] && landmarks[16]) {
    const rVis = (landmarks[11].visibility || 0) + (landmarks[13].visibility || 0) + (landmarks[15].visibility || 0);
    const lVis = (landmarks[12].visibility || 0) + (landmarks[14].visibility || 0) + (landmarks[16].visibility || 0);
    if (lVis > rVis) { shoulder = landmarks[12]; elbow = landmarks[14]; wrist = landmarks[16]; }
  }

  const rawAngle = calculateAngle(shoulder, elbow, wrist);
  const smoothedAngle = smoothAngleFor('bicep_curl', rawAngle);
  updateRepAngleRange(rawAngle);
  document.getElementById("angle-display").textContent = Math.round(smoothedAngle) + "°";

  // Form check — elbow must not swing wildly (relaxed threshold 0.06)
  let isFormCorrect = true, formMsg = "";
  isPositionStable(elbow, elbowPositionHistory, 0.08);  // just track, no fail
  if (hasSignificantMovement(shoulder, shoulderPositionHistory, 0.08)) {
    isFormCorrect = false; formMsg = "⚠️ Don't swing your body!";
  }
  isPositionStable(shoulder, shoulderPositionHistory, 0.08);

  // Stage detection — generous ranges so real users trigger reliably
  const isDown = smoothedAngle >= 150;          // arm straight / extended
  const isUp = smoothedAngle <= 75;           // arm curled up

  let feedback = "", stageText = currentStage || "Ready";

  if (isFormCorrect) {
    validationBuffer++;
    // State machine: null/down → up → down (= 1 rep)
    if (isUp && (currentStage === "down" || currentStage === null) && validationBuffer >= REP_CONFIRM_FRAMES) {
      currentStage = "up"; validationBuffer = 0;
      feedback = "✅ Curled! Now lower fully."; stageText = "Curled";
    } else if (isDown && currentStage === "up" && validationBuffer >= REP_CONFIRM_FRAMES) {
      const r = _countRep("✅ Perfect rep! 💪", "down", "Extended");
      feedback = r.feedback; stageText = r.stageText;
    } else {
      if (currentStage === null || currentStage === "down") {
        feedback = `Curl up! (${Math.round(smoothedAngle)}°)`;
        stageText = "Extend arm";
      } else {
        feedback = `Lower down! (${Math.round(smoothedAngle)}°)`;
        stageText = "Curled";
      }
    }
  } else {
    validationBuffer = 0;
    feedback = formMsg;
  }
  updateFormDisplay(isFormCorrect, feedback, stageText, smoothedAngle);
  window._acpfCurrentAngle = smoothedAngle;
  window._acpfFormOk = isFormCorrect;
}

// ─── SHOULDER PRESS ───────────────────────────────────────────────────────────
// Angle: shoulder(11) - elbow(13) - wrist(15)
// BOTTOM: ~70-100°   TOP (locked out): ~165°+
function analyzeShoulderPressAccurate(landmarks, workout) {
  let shoulder = landmarks[11], elbow = landmarks[13], wrist = landmarks[15];
  if (landmarks[12] && landmarks[14] && landmarks[16]) {
    const rVis = (landmarks[11].visibility || 0) + (landmarks[13].visibility || 0);
    const lVis = (landmarks[12].visibility || 0) + (landmarks[14].visibility || 0);
    if (lVis > rVis) { shoulder = landmarks[12]; elbow = landmarks[14]; wrist = landmarks[16]; }
  }
  const rawAngle = calculateAngle(shoulder, elbow, wrist);
  const smoothedAngle = smoothAngleFor('shoulder_press', rawAngle);
  updateRepAngleRange(rawAngle);
  document.getElementById("angle-display").textContent = Math.round(smoothedAngle) + "°";

  const isTop = smoothedAngle >= 160;
  const isBottom = smoothedAngle <= 105;
  let feedback = "", stageText = currentStage || "Ready";

  validationBuffer++;
  if (isBottom && (currentStage === "up" || currentStage === null) && validationBuffer >= REP_CONFIRM_FRAMES) {
    currentStage = "down"; validationBuffer = 0;
    feedback = "✅ Good depth! Press up!"; stageText = "At Bottom";
  } else if (isTop && currentStage === "down" && validationBuffer >= REP_CONFIRM_FRAMES) {
    const r = _countRep("✅ Powerful press! 🏋️", "up", "Locked Out");
    feedback = r.feedback; stageText = r.stageText;
  } else {
    feedback = currentStage === "down" ? `Press up! (${Math.round(smoothedAngle)}°)` : `Lower down! (${Math.round(smoothedAngle)}°)`;
    stageText = currentStage || "Ready";
  }
  updateFormDisplay(true, feedback, stageText, smoothedAngle);
  window._acpfCurrentAngle = smoothedAngle;
}

// ─── LATERAL RAISE ───────────────────────────────────────────────────────────
// Angle: hip(23) - shoulder(11) - wrist(15)
// DOWN: ~5-35°   TOP (shoulder level): ~80-110°
function analyzeLateralRaiseAccurate(landmarks, workout) {
  const shoulder = landmarks[11], hip = landmarks[23], wrist = landmarks[15];
  const rawAngle = calculateAngle(hip, shoulder, wrist);
  const smoothedAngle = smoothAngleFor('lateral_raise', rawAngle);
  updateRepAngleRange(rawAngle);
  document.getElementById("angle-display").textContent = Math.round(smoothedAngle) + "°";

  const isTop = smoothedAngle >= 75;
  const isBottom = smoothedAngle <= 35;
  let feedback = "", stageText = currentStage || "Ready";

  validationBuffer++;
  if (isTop && (currentStage === "down" || currentStage === null) && validationBuffer >= REP_CONFIRM_FRAMES) {
    currentStage = "up"; validationBuffer = 0;
    feedback = "✅ Good height! Lower slowly."; stageText = "At Top";
  } else if (isBottom && currentStage === "up" && validationBuffer >= REP_CONFIRM_FRAMES) {
    const r = _countRep("✅ Perfect raise! 💪", "down", "Down");
    feedback = r.feedback; stageText = r.stageText;
  } else {
    feedback = currentStage === "up" ? "Lower arms slowly!" : `Raise arms! (${Math.round(smoothedAngle)}°)`;
    stageText = currentStage || "Ready";
  }
  updateFormDisplay(true, feedback, stageText, smoothedAngle);
  window._acpfCurrentAngle = smoothedAngle;
  // Expose raw lateral raise angle for game sync (0=arms down, 100=arms at shoulder)
  window._lateralRaiseAngle = smoothedAngle;
  window._lateralRaiseNorm = Math.min(1, Math.max(0, (smoothedAngle - 10) / 80)); // 0=down, 1=up
}

// ─── SQUAT ────────────────────────────────────────────────────────────────────
// Angle: hip(23) - knee(25) - ankle(27)
// STANDING: ~160-180°   DEEP SQUAT: ~70-100°
function analyzeSquat(landmarks, workout) {
  // Use whichever leg is more visible
  let hip = landmarks[23], knee = landmarks[25], ankle = landmarks[27];
  const rVis = (landmarks[23].visibility || 0) + (landmarks[25].visibility || 0) + (landmarks[27].visibility || 0);
  const lVis = (landmarks[24].visibility || 0) + (landmarks[26].visibility || 0) + (landmarks[28].visibility || 0);
  if (lVis > rVis) { hip = landmarks[24]; knee = landmarks[26]; ankle = landmarks[28]; }

  const rawAngle = calculateAngle(hip, knee, ankle);
  const smoothedAngle = smoothAngleFor('squat', rawAngle);
  updateRepAngleRange(rawAngle);
  document.getElementById("angle-display").textContent = Math.round(smoothedAngle) + "°";

  const isStanding = smoothedAngle >= 155;
  const isSquatted = smoothedAngle <= 105;
  let feedback = "", stageText = currentStage || "Ready";

  validationBuffer++;
  if (isSquatted && (currentStage === "up" || currentStage === null) && validationBuffer >= REP_CONFIRM_FRAMES) {
    currentStage = "down"; validationBuffer = 0;
    feedback = "✅ Good depth! Stand up!"; stageText = "Squatted";
  } else if (isStanding && currentStage === "down" && validationBuffer >= REP_CONFIRM_FRAMES) {
    const r = _countRep("✅ Great squat! 🦵", "up", "Standing");
    feedback = r.feedback; stageText = r.stageText;
  } else {
    if (currentStage === "down") { feedback = `Stand up! (${Math.round(smoothedAngle)}°)`; stageText = "Squat Deep"; }
    else { feedback = `Squat down! (${Math.round(smoothedAngle)}°)`; stageText = "Standing"; }
  }
  // Back alignment check
  const shoulder = landmarks[11], hipPt = landmarks[23];
  const torsoLean = Math.abs(shoulder.x - hipPt.x);
  const isFormOk = torsoLean < 0.18;
  if (!isFormOk) feedback = "⚠️ Keep chest up, don't lean forward!";
  updateFormDisplay(isFormOk, feedback, stageText, smoothedAngle);
  window._acpfCurrentAngle = smoothedAngle; window._acpfFormOk = isFormOk;
}

// ─── PUSHUP ───────────────────────────────────────────────────────────────────
// Angle: shoulder(11) - elbow(13) - wrist(15)
// UP (arms extended): ~160°+   DOWN (chest near floor): ~70-90°
function analyzePushup(landmarks, workout) {
  let shoulder = landmarks[11], elbow = landmarks[13], wrist = landmarks[15];
  const rVis = (landmarks[11].visibility || 0) + (landmarks[13].visibility || 0);
  const lVis = (landmarks[12].visibility || 0) + (landmarks[14].visibility || 0);
  if (lVis > rVis) { shoulder = landmarks[12]; elbow = landmarks[14]; wrist = landmarks[16]; }

  const rawAngle = calculateAngle(shoulder, elbow, wrist);
  const smoothedAngle = smoothAngleFor('pushup', rawAngle);
  updateRepAngleRange(rawAngle);
  document.getElementById("angle-display").textContent = Math.round(smoothedAngle) + "°";

  const isUp = smoothedAngle >= 150;
  const isDown = smoothedAngle <= 90;
  let feedback = "", stageText = currentStage || "Ready";

  validationBuffer++;
  if (isDown && (currentStage === "up" || currentStage === null) && validationBuffer >= REP_CONFIRM_FRAMES) {
    currentStage = "down"; validationBuffer = 0;
    feedback = "✅ Good depth! Push up!"; stageText = "Down";
  } else if (isUp && currentStage === "down" && validationBuffer >= REP_CONFIRM_FRAMES) {
    const r = _countRep("✅ Great pushup! 💪", "up", "Up");
    feedback = r.feedback; stageText = r.stageText;
  } else {
    feedback = currentStage === "down" ? `Push up! (${Math.round(smoothedAngle)}°)` : `Go down! (${Math.round(smoothedAngle)}°)`;
    stageText = currentStage || "Ready";
  }
  // Body alignment: hip should not sag or pike
  const hip = landmarks[23], ankleP = landmarks[27];
  const bodyLine = Math.abs((hip.y - shoulder.y) - (ankleP.y - hip.y) * 0.5);
  const isFormOk = bodyLine < 0.12;
  if (!isFormOk) feedback = "⚠️ Keep body straight — no sagging!";
  updateFormDisplay(isFormOk, feedback, stageText, smoothedAngle);
  window._acpfCurrentAngle = smoothedAngle; window._acpfFormOk = isFormOk;
}

// ─── DEADLIFT ─────────────────────────────────────────────────────────────────
// Angle: shoulder(11) - hip(23) - knee(25)
// STANDING: ~170°+   HINGE (bar at floor): ~60-90°
function analyzeDeadlift(landmarks, workout) {
  const shoulder = landmarks[11], hip = landmarks[23], knee = landmarks[25];
  const rawAngle = calculateAngle(shoulder, hip, knee);
  const smoothedAngle = smoothAngleFor('deadlift', rawAngle);
  updateRepAngleRange(rawAngle);
  document.getElementById("angle-display").textContent = Math.round(smoothedAngle) + "°";

  const isUp = smoothedAngle >= 160;
  const isDown = smoothedAngle <= 100;
  let feedback = "", stageText = currentStage || "Ready";

  validationBuffer++;
  if (isDown && (currentStage === "up" || currentStage === null) && validationBuffer >= REP_CONFIRM_FRAMES) {
    currentStage = "down"; validationBuffer = 0;
    feedback = "✅ Good hinge! Drive through heels!"; stageText = "Hinged";
  } else if (isUp && currentStage === "down" && validationBuffer >= REP_CONFIRM_FRAMES) {
    const r = _countRep("✅ Strong lift! 🏋️", "up", "Standing");
    feedback = r.feedback; stageText = r.stageText;
  } else {
    feedback = currentStage === "down" ? "Stand tall!" : `Hinge at hips! (${Math.round(smoothedAngle)}°)`;
    stageText = currentStage || "Ready";
  }
  updateFormDisplay(true, feedback, stageText, smoothedAngle);
  window._acpfCurrentAngle = smoothedAngle;
}

// ─── PLANK ────────────────────────────────────────────────────────────────────
// Angle: ankle(27) - hip(23) - shoulder(11) — should be ~165-180° (straight body)
function analyzePlank(landmarks, workout) {
  const ankle = landmarks[27], hip = landmarks[23], shoulder = landmarks[11];
  const rawAngle = calculateAngle(ankle, hip, shoulder);
  const smoothedAngle = smoothAngleFor('plank', rawAngle);
  document.getElementById("angle-display").textContent = Math.round(smoothedAngle) + "°";

  let feedback = "", isFormOk = true;
  if (smoothedAngle >= 162 && smoothedAngle <= 185) {
    feedback = "✅ Perfect plank! Keep holding!";
  } else if (smoothedAngle < 162) {
    feedback = "⚠️ Lift hips! Keep body straight."; isFormOk = false;
  } else {
    feedback = "⚠️ Lower hips slightly!"; isFormOk = false;
  }
  updateFormDisplay(isFormOk, feedback, "Holding", smoothedAngle);
  window._acpfCurrentAngle = smoothedAngle; window._acpfFormOk = isFormOk;
}

// ─── LUNGES ───────────────────────────────────────────────────────────────────
// Front knee angle: hip(23) - knee(25) - ankle(27)
// STANDING: ~165°+   LUNGE: ~85-95°
function analyzeLunges(landmarks, workout) {
  let hip = landmarks[23], knee = landmarks[25], ankle = landmarks[27];
  const rVis = (landmarks[25].visibility || 0);
  const lVis = (landmarks[26].visibility || 0);
  if (lVis > rVis) { hip = landmarks[24]; knee = landmarks[26]; ankle = landmarks[28]; }

  const rawAngle = calculateAngle(hip, knee, ankle);
  const smoothedAngle = smoothAngleFor('lunges', rawAngle);
  updateRepAngleRange(rawAngle);
  document.getElementById("angle-display").textContent = Math.round(smoothedAngle) + "°";

  const isUp = smoothedAngle >= 155;
  const isDown = smoothedAngle <= 100;
  let feedback = "", stageText = currentStage || "Ready";

  validationBuffer++;
  if (isDown && (currentStage === "up" || currentStage === null) && validationBuffer >= REP_CONFIRM_FRAMES) {
    currentStage = "down"; validationBuffer = 0;
    feedback = "✅ Good lunge! Drive up!"; stageText = "Lunged";
  } else if (isUp && currentStage === "down" && validationBuffer >= REP_CONFIRM_FRAMES) {
    const r = _countRep("✅ Great lunge! 🦵", "up", "Standing");
    feedback = r.feedback; stageText = r.stageText;
  } else {
    feedback = currentStage === "down" ? "Drive up!" : `Step forward! (${Math.round(smoothedAngle)}°)`;
    stageText = currentStage || "Ready";
  }
  updateFormDisplay(true, feedback, stageText, smoothedAngle);
  window._acpfCurrentAngle = smoothedAngle;
}

// ─── PULL UP ─────────────────────────────────────────────────────────────────
// Angle: shoulder(11) - elbow(13) - wrist(15)
// HANGING (arms extended): ~165°+   UP (chin over bar): ~50-70°
function analyzePullUp(landmarks, workout) {
  let shoulder = landmarks[11], elbow = landmarks[13], wrist = landmarks[15];
  const rVis = (landmarks[11].visibility || 0) + (landmarks[13].visibility || 0);
  const lVis = (landmarks[12].visibility || 0) + (landmarks[14].visibility || 0);
  if (lVis > rVis) { shoulder = landmarks[12]; elbow = landmarks[14]; wrist = landmarks[16]; }

  const rawAngle = calculateAngle(shoulder, elbow, wrist);
  const smoothedAngle = smoothAngleFor('pull_up', rawAngle);
  updateRepAngleRange(rawAngle);
  document.getElementById("angle-display").textContent = Math.round(smoothedAngle) + "°";

  const isUp = smoothedAngle <= 75;   // arms bent, chin at bar
  const isHanging = smoothedAngle >= 155;   // arms extended
  let feedback = "", stageText = currentStage || "Ready";

  validationBuffer++;
  if (isUp && (currentStage === "down" || currentStage === null) && validationBuffer >= REP_CONFIRM_FRAMES) {
    currentStage = "up"; validationBuffer = 0;
    feedback = "✅ Chin over bar! Lower down."; stageText = "At Top";
  } else if (isHanging && currentStage === "up" && validationBuffer >= REP_CONFIRM_FRAMES) {
    const r = _countRep("✅ Full rep! 💪", "down", "Hanging");
    feedback = r.feedback; stageText = r.stageText;
  } else {
    feedback = currentStage === "up" ? "Lower down fully!" : `Pull up! (${Math.round(smoothedAngle)}°)`;
    stageText = currentStage || "Ready";
  }
  updateFormDisplay(true, feedback, stageText, smoothedAngle);
  window._acpfCurrentAngle = smoothedAngle;
}

// ─── DIPS ─────────────────────────────────────────────────────────────────────
// Angle: shoulder(11) - elbow(13) - wrist(15) same as pushup but vertical
// UP: ~155°+   DOWN: ~70-85°
function analyzeDips(landmarks, workout) {
  let shoulder = landmarks[11], elbow = landmarks[13], wrist = landmarks[15];
  const rVis = (landmarks[11].visibility || 0) + (landmarks[13].visibility || 0);
  const lVis = (landmarks[12].visibility || 0) + (landmarks[14].visibility || 0);
  if (lVis > rVis) { shoulder = landmarks[12]; elbow = landmarks[14]; wrist = landmarks[16]; }

  const rawAngle = calculateAngle(shoulder, elbow, wrist);
  const smoothedAngle = smoothAngleFor('dips', rawAngle);
  updateRepAngleRange(rawAngle);
  document.getElementById("angle-display").textContent = Math.round(smoothedAngle) + "°";

  const isUp = smoothedAngle >= 150;
  const isDown = smoothedAngle <= 90;
  let feedback = "", stageText = currentStage || "Ready";

  validationBuffer++;
  if (isDown && (currentStage === "up" || currentStage === null) && validationBuffer >= REP_CONFIRM_FRAMES) {
    currentStage = "down"; validationBuffer = 0;
    feedback = "✅ Good depth! Push up!"; stageText = "Dipped";
  } else if (isUp && currentStage === "down" && validationBuffer >= REP_CONFIRM_FRAMES) {
    const r = _countRep("✅ Strong dip! 💪", "up", "Up");
    feedback = r.feedback; stageText = r.stageText;
  } else {
    feedback = currentStage === "down" ? "Push up!" : `Dip down! (${Math.round(smoothedAngle)}°)`;
    stageText = currentStage || "Ready";
  }
  updateFormDisplay(true, feedback, stageText, smoothedAngle);
  window._acpfCurrentAngle = smoothedAngle;
}

// ─── BENCH PRESS ──────────────────────────────────────────────────────────────
// Angle: shoulder(11) - elbow(13) - wrist(15)
// TOP (locked out): ~160°+   BOTTOM (bar to chest): ~70-90°
function analyzeBenchPress(landmarks, workout) {
  let shoulder = landmarks[11], elbow = landmarks[13], wrist = landmarks[15];
  const rVis = (landmarks[11].visibility || 0) + (landmarks[13].visibility || 0);
  const lVis = (landmarks[12].visibility || 0) + (landmarks[14].visibility || 0);
  if (lVis > rVis) { shoulder = landmarks[12]; elbow = landmarks[14]; wrist = landmarks[16]; }

  const rawAngle = calculateAngle(shoulder, elbow, wrist);
  const smoothedAngle = smoothAngleFor('bench_press', rawAngle);
  updateRepAngleRange(rawAngle);
  document.getElementById("angle-display").textContent = Math.round(smoothedAngle) + "°";

  const isTop = smoothedAngle >= 155;
  const isBottom = smoothedAngle <= 90;
  let feedback = "", stageText = currentStage || "Ready";

  validationBuffer++;
  if (isBottom && (currentStage === "up" || currentStage === null) && validationBuffer >= REP_CONFIRM_FRAMES) {
    currentStage = "down"; validationBuffer = 0;
    feedback = "✅ Full range! Press up!"; stageText = "Lowered";
  } else if (isTop && currentStage === "down" && validationBuffer >= REP_CONFIRM_FRAMES) {
    const r = _countRep("✅ Strong press! 🏋️", "up", "Pressed");
    feedback = r.feedback; stageText = r.stageText;
  } else {
    feedback = currentStage === "down" ? "Press up!" : `Lower down! (${Math.round(smoothedAngle)}°)`;
    stageText = currentStage || "Ready";
  }
  updateFormDisplay(true, feedback, stageText, smoothedAngle);
  window._acpfCurrentAngle = smoothedAngle;
}

// ─── BARBELL ROW ──────────────────────────────────────────────────────────────
// Angle: shoulder(11) - elbow(13) — elbow goes from extended to pulled back
// Use wrist-elbow-shoulder: EXTENDED: ~150°+   PULLED: ~50-70°
function analyzeBarbellRow(landmarks, workout) {
  let shoulder = landmarks[11], elbow = landmarks[13], wrist = landmarks[15];
  const rVis = (landmarks[11].visibility || 0) + (landmarks[13].visibility || 0);
  const lVis = (landmarks[12].visibility || 0) + (landmarks[14].visibility || 0);
  if (lVis > rVis) { shoulder = landmarks[12]; elbow = landmarks[14]; wrist = landmarks[16]; }

  const rawAngle = calculateAngle(wrist, elbow, shoulder);
  const smoothedAngle = smoothAngleFor('barbell_row', rawAngle);
  updateRepAngleRange(rawAngle);
  document.getElementById("angle-display").textContent = Math.round(smoothedAngle) + "°";

  const isPulled = smoothedAngle <= 70;
  const isExtended = smoothedAngle >= 145;
  let feedback = "", stageText = currentStage || "Ready";

  validationBuffer++;
  if (isPulled && (currentStage === "down" || currentStage === null) && validationBuffer >= REP_CONFIRM_FRAMES) {
    currentStage = "up"; validationBuffer = 0;
    feedback = "✅ Good pull! Lower to start."; stageText = "Pulled";
  } else if (isExtended && currentStage === "up" && validationBuffer >= REP_CONFIRM_FRAMES) {
    const r = _countRep("✅ Full rep! 💪", "down", "Extended");
    feedback = r.feedback; stageText = r.stageText;
  } else {
    feedback = currentStage === "up" ? "Extend arms!" : `Row up! (${Math.round(smoothedAngle)}°)`;
    stageText = currentStage || "Ready";
  }
  updateFormDisplay(true, feedback, stageText, smoothedAngle);
  window._acpfCurrentAngle = smoothedAngle;
}

function updateFormDisplay(isCorrect, feedback, stage, angle) {
  const formStatus = document.getElementById("form-status");
  const formDisplay = document.getElementById("form-display");
  const stageDisplay = document.getElementById("stage-display");
  if (formDisplay) formDisplay.textContent = feedback;
  if (stageDisplay) stageDisplay.textContent = stage || "-";
  if (formStatus) {
    formStatus.style.backgroundColor = isCorrect
      ? "rgba(16,185,129,0.2)"
      : "rgba(239,68,68,0.2)";
    if (formDisplay) formDisplay.style.color = isCorrect ? "#10b981" : "#ef4444";
  }
}

function checkGoalReached() {
  if (repCounter >= targetReps) {
    playSound("goal");
    setTimeout(() => alert(`🎉 Congratulations! You've completed ${targetReps} reps! Great work!`), 500);
  }
}

function playSound(type) {
  const ids = { success: "success-sound", error: "error-sound", goal: "goal-sound" };
  const audio = document.getElementById(ids[type]);
  if (audio) {
    audio.currentTime = 0;
    audio.play().catch(e => console.log("Audio play blocked:", e));
  }
}

// ============================================================
// ACPF COGNITIVE FITNESS SYSTEM — JavaScript Integration
// Added to FitPulse Pro for real-time cognitive monitoring
// ============================================================

// ── State ────────────────────────────────────────────────────
let cognitivePollingInterval = null;
let acpfSessionStartTime = null;   // renamed to avoid collision with personal trainer var
let cognitiveFrameCanvas = null;
let cognitiveFrameCtx = null;
let acpfSessionActive = false;
let currentExerciseType = 'strength';

// Map exercise name to type for ACPF
const EXERCISE_TYPE_MAP = {
  'bicep_curl': 'strength',
  'squat': 'strength',
  'pushup': 'strength',
  'shoulder_press': 'strength',
  'deadlift': 'strength',
  'plank': 'balance',
  'lunges': 'strength',
  'pull_up': 'strength',
  'dips': 'strength',
  'bench_press': 'strength',
  'lateral_raise': 'strength',
  'barbell_row': 'strength'
};

// ── Off-screen canvas for frame capture ────────────────────
function initCognitiveCanvas() {
  cognitiveFrameCanvas = document.createElement('canvas');
  cognitiveFrameCanvas.width = 320;
  cognitiveFrameCanvas.height = 240;
  cognitiveFrameCtx = cognitiveFrameCanvas.getContext('2d');
}

// ── Capture current video frame as base64 JPEG ─────────────
function captureFrameBase64() {
  const video = document.getElementById('pose-video');
  if (!video || video.readyState < 2) return null;
  if (!cognitiveFrameCtx) initCognitiveCanvas();

  cognitiveFrameCtx.drawImage(video, 0, 0,
    cognitiveFrameCanvas.width, cognitiveFrameCanvas.height);
  return cognitiveFrameCanvas.toDataURL('image/jpeg', 0.7);
}

// ── Get shoulder landmarks from MediaPipe (for breathing) ──
function getShoulderLandmarks() {
  // These are updated inside onPoseResults via global variable
  return window._lastShoulderLandmarks || {};
}

// ── Build physical state payload from real tracked values ───
// Uses window._acpfCurrentAngle, window._acpfFormOk and window._acpfRepCount
// set by the exercise analysis functions in real time.
function buildPhysicalPayload() {
  const angle = window._acpfCurrentAngle || 0;
  const reps = window._acpfRepCount || repCounter || 0;
  const formOk = window._acpfFormOk !== undefined ? window._acpfFormOk : true;

  // Form score: starts at 80 (good), degrades based on form violations & rep progress
  const formText = document.getElementById('form-display')?.textContent || '';
  let formScore = 80;
  if (!formOk || formText.includes('⚠️')) formScore = 42;
  else if (formText.includes('✅')) formScore = 90;
  else if (formText.includes('⛔')) formScore = 18;

  // Range of motion — derived from actual angle range seen during reps
  const rom = Math.min(100, getRepROM());

  // Smoothness — stays high when form is good, drops when form warns fire
  const smoothness = formOk ? Math.min(100, 65 + reps * 2) : 40;

  return {
    form_score: formScore,
    range_of_motion: rom > 5 ? rom : 65,  // fallback while calibrating
    movement_smoothness: smoothness,
    rep_count: reps,
    angle: Math.round(angle)
  };
}

// ── Start cognitive session (called when workout starts) ────
async function startCognitiveSession(exerciseName, exerciseType) {
  acpfSessionActive = true;
  acpfSessionStartTime = Date.now();
  currentExerciseType = exerciseType || EXERCISE_TYPE_MAP[exerciseName] || 'strength';

  // Notify dots: loading state
  setStatusDots('loading');

  try {
    await apiFetch('/cognitive/start-session', {
      method: 'POST',
      body: JSON.stringify({
        exercise_type: currentExerciseType,
        athlete_name: 'Athlete',
        exercise_name: exerciseName
      })
    });
    console.log('[ACPF] Cognitive session started:', exerciseName);
  } catch (e) {
    console.warn('[ACPF] Could not start cognitive session:', e);
  }

  // Begin polling
  initCognitiveCanvas();
  startCognitivePolling();
}

// ── Stop cognitive session ──────────────────────────────────
function stopCognitiveSession() {
  acpfSessionActive = false;
  stopCognitivePolling();

  // Show dashboard button after session ends
  if (window._acpfHasData) {
    const btn = document.getElementById('download-dashboard-btn');
    const btn2 = document.getElementById('main-dashboard-btn');
    if (btn) btn.style.display = 'block';
    if (btn2) btn2.style.display = 'inline-flex';
  }
  setStatusDots('error');
}

// ── Polling ─────────────────────────────────────────────────
function startCognitivePolling() {
  if (cognitivePollingInterval) clearInterval(cognitivePollingInterval);
  cognitivePollingInterval = setInterval(runCognitiveFrame, 1500); // every 1.5s
}

function stopCognitivePolling() {
  if (cognitivePollingInterval) {
    clearInterval(cognitivePollingInterval);
    cognitivePollingInterval = null;
  }
}

// ── Core: send frame to backend, update UI ──────────────────
async function runCognitiveFrame() {
  if (!acpfSessionActive) return;

  const b64Frame = captureFrameBase64();
  const shoulders = getShoulderLandmarks();
  const physical = buildPhysicalPayload();
  const sessionDur = (Date.now() - (acpfSessionStartTime || Date.now())) / 1000;

  const payload = {
    frame: b64Frame,
    shoulder_landmarks: shoulders,
    physical: physical,
    session_duration: sessionDur,
    exercise_type: currentExerciseType
  };

  try {
    const resp = await apiFetch('/cognitive/process-frame', {
      method: 'POST',
      body: JSON.stringify(payload)
    });

    if (!resp.ok) return;
    const json = await resp.json();
    if (json.status !== 'ok') return;

    const d = json.data;
    window._acpfHasData = true;
    setStatusDots('active');

    updateCognitiveUI(d);

  } catch (e) {
    console.warn('[ACPF] Frame processing error:', e);
    setStatusDots('loading');
  }
}

// ── Update all cognitive UI elements ───────────────────────
function updateCognitiveUI(data) {
  const { emotion, gaze, breathing, sf, acpf } = data;

  // ── Emotion ───────────────────────────────────────────────
  if (emotion && !emotion.error) {
    safeText('emotion-val', emotion.fitness_status || emotion.emotion);
    safeText('emotion-message', emotion.message || '');
    safeStyle('emotion-val', 'color', emotion.color || '#22d3ee');
  }

  // ── Focus ─────────────────────────────────────────────────
  if (gaze && !gaze.error) {
    const fs = gaze.focus_score || 0;
    safeText('focus-val', `${fs}%`);
    safeWidth('focus-progress', fs);
    safeText('focus-eyes', `L: ${gaze.left_eye || '--'} | R: ${gaze.right_eye || '--'}`);
  }

  // ── Breathing ─────────────────────────────────────────────
  if (breathing && !breathing.error) {
    const bpm = breathing.bpm;
    safeText('breathing-val', bpm > 0 ? `${bpm} BPM` : '-- BPM');
    safeText('breathing-pattern', breathing.status_message || breathing.pattern || '');
  }

  // ── Stress / Fatigue / Motivation ────────────────────────
  if (sf && !sf.error) {
    const stress = sf.stress || 0;
    const fat = sf.fatigue || 0;
    const mot = sf.motivation || 0;

    safeText('stress-val', `${stress}%`);
    safeWidth('stress-progress', stress);
    safeText('stress-message', sf.stress_message || '');
    safeStyle('stress-progress', 'background', sf.stress_color || '#ef4444');

    safeText('fatigue-val', `${fat}%`);
    safeWidth('fatigue-progress', fat);
    safeText('fatigue-message', sf.fatigue_message || '');

    safeText('motivation-val', `${mot}%`);
    safeWidth('motivation-progress', mot);
    safeText('motivation-message', sf.motivation_message || '');
  }

  // ── ACPF ─────────────────────────────────────────────────
  if (acpf && !acpf.error) {
    const score = Math.round(acpf.acpf_score || acpf.overall_wellness || 0);
    const risk = (acpf.risk_level || 'SAFE').toUpperCase();
    const action = acpf.recommended_action || '';
    const trend = acpf.trend || {};

    safeText('acpf-score-val', `${score}`);
    safeWidth('acpf-progress', score);
    safeText('acpf-action-text', action);

    // Wellness overall
    safeText('wellness-val', `${score}/100`);
    const dir = trend.direction || 'stable';
    const arrow = dir === 'improving' ? '📈 Improving' : (dir === 'declining' ? '📉 Declining' : '➡️ Stable');
    safeText('wellness-trend-text', `${arrow} (${trend.confidence || '?'} confidence)`);

    // Risk banner on video
    updateRiskBanner(risk, action);
  }
}

// ── Risk banner on video ───────────────────────────────────
function updateRiskBanner(risk, message) {
  const banner = document.getElementById('acpf-risk-banner');
  if (!banner) return;

  if (risk === 'STOP') {
    banner.className = 'acpf-risk-banner stop';
    banner.textContent = message;
    banner.style.display = 'block';
  } else if (risk === 'CAUTION') {
    banner.className = 'acpf-risk-banner caution';
    banner.textContent = message;
    banner.style.display = 'block';
  } else {
    banner.style.display = 'none';
  }
}

// ── Download ACPF Dashboard ────────────────────────────────
async function downloadACPFDashboard() {
  try {
    const resp = await apiFetch('/cognitive/download-dashboard', {
      method: 'POST',
      body: JSON.stringify({})
    });

    if (!resp.ok) {
      alert('⚠️ No session data available yet. Complete a workout first!');
      return;
    }

    const html = await resp.text();
    const blob = new Blob([html], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ACPF_Dashboard_${Date.now()}.html`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

  } catch (e) {
    alert('Error generating dashboard: ' + e.message);
  }
}
window.downloadACPFDashboard = downloadACPFDashboard;

// ── Status dot helper ──────────────────────────────────────
function setStatusDots(state) {
  ['emotion', 'gaze', 'breathing'].forEach(name => {
    const dot = document.getElementById(`status-dot-${name}`);
    if (dot) {
      dot.className = `status-dot ${state}`;
    }
  });
}

// ── DOM helpers ───────────────────────────────────────────
function safeText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}
function safeStyle(id, prop, val) {
  const el = document.getElementById(id);
  if (el) el.style[prop] = val;
}
function safeWidth(id, pct) {
  const el = document.getElementById(id);
  if (el) el.style.width = `${Math.min(100, Math.max(0, pct))}%`;
}

// ── Safe hooks — installed after DOM is fully ready ────────
// We do NOT reassign window.startWorkout or window.stopWorkout.
// Instead, the existing startWorkout / stopWorkout functions
// call acpfOnWorkoutStarted() / acpfOnWorkoutStopped() directly.
// Those two functions are defined below and called at the bottom
// of startWorkout and stopWorkout via the _acpfHooksInstalled flag.

window._acpfHooksInstalled = false;

function acpfOnWorkoutStarted() {
  setTimeout(() => {
    const exName = currentWorkout || 'exercise';
    const exType = EXERCISE_TYPE_MAP[exName] || 'strength';
    startCognitiveSession(exName, exType);
  }, 2500);
}

function acpfOnWorkoutStopped() {
  stopCognitiveSession();
}

// ── Install hooks safely after load ────────────────────────
window.addEventListener('load', function installACPFHooks() {
  if (window._acpfHooksInstalled) return;
  window._acpfHooksInstalled = true;

  // Patch startWorkout — append cognitive call without replacing it
  const _origStart = startWorkout;
  window.startWorkout = async function () {
    await _origStart.apply(this, arguments);
    acpfOnWorkoutStarted();
  };

  // Patch stopWorkout — prepend cognitive call without replacing it
  const _origStop = stopWorkout;
  window.stopWorkout = function () {
    acpfOnWorkoutStopped();
    _origStop.apply(this, arguments);
  };

  // Re-expose patched functions so onclick= attributes keep working
  window.startWorkout = window.startWorkout;
  window.stopWorkout = window.stopWorkout;
  window.downloadACPFDashboard = downloadACPFDashboard;

  console.log('[ACPF] ✅ Cognitive hooks installed safely.');
});

console.log('[ACPF] Cognitive modules loaded and ready. 🧠');