// =============================================
// QUANTUMCHAT — VOICE CALL  (WebRTC)
// =============================================

const callSocket = (typeof socket !== 'undefined') ? socket : io();

const STUN = {
  iceServers: [
    { urls: 'stun:stun.l.google.com:19302' },
    { urls: 'stun:stun1.l.google.com:19302' },
  ]
};

let peer        = null;
let localStream = null;
let callState   = 'idle';
let remoteUser  = null;
let timerStart  = null;
let timerInt    = null;

const ME    = typeof CURRENT_USER !== 'undefined' ? CURRENT_USER : '';
const OTHER = typeof OTHER_USER   !== 'undefined' ? OTHER_USER   : '';

// ── Inject UI ──
function injectUI() {
  if (document.getElementById('incomingOverlay')) return;
  document.body.insertAdjacentHTML('beforeend', `
    <div id="incomingOverlay" class="call-overlay hidden">
      <div class="call-modal">
        <div class="call-avatar-wrap">
          <div class="call-avatar" id="inAvatar">?</div>
          <div class="ring r1"></div><div class="ring r2"></div><div class="ring r3"></div>
        </div>
        <div class="call-name"   id="inName">Someone</div>
        <div class="call-status">Incoming voice call...</div>
        <div class="call-actions">
          <button class="call-btn decline" id="btnDecline">✕</button>
          <button class="call-btn accept"  id="btnAccept">✓</button>
        </div>
      </div>
    </div>

    <div id="activeOverlay" class="call-overlay hidden">
      <div class="call-modal">
        <div class="call-avatar-wrap">
          <div class="call-avatar" id="acAvatar">?</div>
        </div>
        <div class="call-name"   id="acName">...</div>
        <div class="call-status" id="acStatus">Calling...</div>
        <div class="call-timer"  id="acTimer">00:00</div>
        <div class="call-actions">
          <button class="call-btn mute" id="btnMute">🎤</button>
          <button class="call-btn end"  id="btnEnd">📵</button>
        </div>
      </div>
    </div>
  `);

  document.getElementById('btnAccept') .addEventListener('click', acceptCall);
  document.getElementById('btnDecline').addEventListener('click', declineCall);
  document.getElementById('btnEnd')    .addEventListener('click', endCall);
  document.getElementById('btnMute')   .addEventListener('click', toggleMute);
}

// ── Call button already in template (id=callInitBtn) ──
function bindCallBtn() {
  const btn = document.getElementById('callInitBtn');
  if (btn) btn.addEventListener('click', startCall);
}

// ── Flow ──
async function startCall() {
  if (callState !== 'idle' || !OTHER) return;
  callState  = 'calling';
  remoteUser = OTHER;
  try {
    localStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    toast('Microphone access denied.'); callState = 'idle'; return;
  }
  showActive(OTHER, 'Ringing...');
  callSocket.emit('call_user', { target: OTHER });
}

function acceptCall() {
  if (callState !== 'receiving') return;
  hideIncoming();
  showActive(remoteUser, 'Connecting...');
  navigator.mediaDevices.getUserMedia({ audio: true })
    .then(stream => {
      localStream = stream;
      createPeer(false);
      callSocket.emit('call_accepted', { target: remoteUser });
    })
    .catch(() => { toast('Microphone access denied.'); cleanup(); });
}

function declineCall() {
  callSocket.emit('call_declined', { target: remoteUser });
  cleanup(); hideIncoming();
}

function endCall() {
  callSocket.emit('call_ended', { target: remoteUser });
  cleanup(); hideActive(); toast('Call ended.');
}

function toggleMute() {
  if (!localStream) return;
  const btn   = document.getElementById('btnMute');
  const track = localStream.getAudioTracks()[0];
  if (!track) return;
  track.enabled = !track.enabled;
  btn.textContent = track.enabled ? '🎤' : '🔇';
  btn.classList.toggle('muted', !track.enabled);
}

// ── WebRTC ──
function createPeer(initiator) {
  peer = new RTCPeerConnection(STUN);
  localStream.getTracks().forEach(t => peer.addTrack(t, localStream));

  peer.ontrack = e => {
    const audio = document.getElementById('remoteAudio');
    if (audio) { audio.srcObject = e.streams[0]; audio.play().catch(() => {}); }
  };

  peer.onicecandidate = e => {
    if (e.candidate) callSocket.emit('ice_candidate', { target: remoteUser, candidate: e.candidate });
  };

  peer.onconnectionstatechange = () => {
    const s = peer?.connectionState;
    if (s === 'connected') {
      startTimer();
      const st = document.getElementById('acStatus');
      if (st) st.textContent = 'Connected';
    }
    if (s === 'disconnected' || s === 'failed' || s === 'closed') {
      cleanup(); hideActive(); toast('Call disconnected.');
    }
  };

  if (initiator) {
    peer.createOffer()
      .then(o => peer.setLocalDescription(o))
      .then(() => callSocket.emit('offer', { target: remoteUser, sdp: peer.localDescription }));
  }
}

// ── Socket events ──
callSocket.on('incoming_call', data => {
  if (callState !== 'idle') { callSocket.emit('call_declined', { target: data.caller }); return; }
  callState  = 'receiving';
  remoteUser = data.caller;
  showIncoming(data.caller);
});

callSocket.on('call_accepted', () => {
  if (callState !== 'calling') return;
  callState = 'active';
  const st = document.getElementById('acStatus');
  if (st) st.textContent = 'Connecting...';
  createPeer(true);
});

callSocket.on('call_declined', () => { cleanup(); hideActive(); toast('Call declined.'); });
callSocket.on('call_ended',    () => { cleanup(); hideActive(); hideIncoming(); toast(`${remoteUser || 'They'} ended the call.`); });

callSocket.on('offer', async data => {
  if (!peer) return;
  await peer.setRemoteDescription(new RTCSessionDescription(data.sdp));
  const ans = await peer.createAnswer();
  await peer.setLocalDescription(ans);
  callSocket.emit('answer', { target: remoteUser, sdp: peer.localDescription });
});

callSocket.on('answer', async data => {
  if (!peer) return;
  await peer.setRemoteDescription(new RTCSessionDescription(data.sdp));
  callState = 'active';
});

callSocket.on('ice_candidate', async data => {
  if (!peer || !data.candidate) return;
  try { await peer.addIceCandidate(new RTCIceCandidate(data.candidate)); } catch {}
});

// ── UI helpers ──
function showIncoming(caller) {
  document.getElementById('inAvatar').textContent = caller[0].toUpperCase();
  document.getElementById('inName').textContent   = caller;
  document.getElementById('incomingOverlay').classList.remove('hidden');
}
function hideIncoming() { document.getElementById('incomingOverlay')?.classList.add('hidden'); }

function showActive(name, status) {
  document.getElementById('acAvatar').textContent = name[0].toUpperCase();
  document.getElementById('acName').textContent   = name;
  document.getElementById('acStatus').textContent = status;
  document.getElementById('acTimer').style.display = 'none';
  document.getElementById('activeOverlay').classList.remove('hidden');
}
function hideActive() { document.getElementById('activeOverlay')?.classList.add('hidden'); stopTimer(); }

function startTimer() {
  timerStart = Date.now();
  const el = document.getElementById('acTimer');
  if (el) el.style.display = 'block';
  timerInt = setInterval(() => {
    const s = Math.floor((Date.now() - timerStart) / 1000);
    const m = Math.floor(s / 60).toString().padStart(2,'0');
    const sec = (s % 60).toString().padStart(2,'0');
    if (el) el.textContent = `${m}:${sec}`;
  }, 1000);
}
function stopTimer()  { clearInterval(timerInt); timerInt = null; }

function cleanup() {
  if (peer)        { peer.close(); peer = null; }
  if (localStream) { localStream.getTracks().forEach(t => t.stop()); localStream = null; }
  stopTimer();
  callState = 'idle'; remoteUser = null;
}

function toast(msg) {
  let t = document.getElementById('callToast');
  if (!t) {
    t = document.createElement('div');
    t.id = 'callToast';
    t.style.cssText = 'position:fixed;bottom:24px;left:50%;transform:translateX(-50%) translateY(8px);background:rgba(17,20,30,0.95);border:1px solid rgba(255,255,255,0.1);border-radius:8px;padding:10px 20px;font-size:13px;color:#fff;z-index:99998;opacity:0;transition:opacity 0.2s,transform 0.2s;white-space:nowrap;font-family:Inter,sans-serif;';
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.style.opacity = '1'; t.style.transform = 'translateX(-50%) translateY(0)';
  setTimeout(() => { t.style.opacity = '0'; t.style.transform = 'translateX(-50%) translateY(8px)'; }, 3000);
}

// ── Init ──
document.addEventListener('DOMContentLoaded', () => { injectUI(); bindCallBtn(); });
injectUI(); bindCallBtn();
