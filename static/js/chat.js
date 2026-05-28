const socket = io();

socket.emit('join', { thread: THREAD_ID });

const input      = document.getElementById('messageInput');
const sendBtn    = document.getElementById('sendBtn');
const msgArea    = document.getElementById('messagesArea');
const typingEl   = document.getElementById('typingIndicator');
const noMessages = document.getElementById('noMessages');

let typingTimer;

function timeNow() {
  const d = new Date();
  return `${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}`;
}

function appendMessage(content, isMine, senderName) {
  if (noMessages) noMessages.remove();
  const wrap = document.createElement('div');
  wrap.className = `msg-wrap ${isMine ? 'sent' : 'received'}`;
  wrap.innerHTML = `
    <div class="msg-meta">${isMine ? 'You' : senderName} · ${timeNow()}</div>
    <div class="bubble"></div>
  `;
  wrap.querySelector('.bubble').textContent = content;
  msgArea.insertBefore(wrap, typingEl);
  msgArea.scrollTop = msgArea.scrollHeight;
}

function sendMessage() {
  const text = input.value.trim();
  if (!text) return;
  socket.emit('send_message', { thread: THREAD_ID, message: text });
  appendMessage(text, true, CURRENT_USER);
  input.value = '';
  socket.emit('stop_typing', { thread: THREAD_ID });
}

sendBtn.addEventListener('click', sendMessage);
input.addEventListener('keydown', e => {
  if (e.key === 'Enter') { e.preventDefault(); sendMessage(); return; }
  socket.emit('typing', { thread: THREAD_ID });
  clearTimeout(typingTimer);
  typingTimer = setTimeout(() => socket.emit('stop_typing', { thread: THREAD_ID }), 1000);
});

socket.on('receive_message', data => {
  if (String(data.thread) !== String(THREAD_ID)) return;
  if (data.sender === CURRENT_USER) return;
  appendMessage(data.message, false, data.sender);
});

socket.on('typing', data => {
  if (data.user !== CURRENT_USER) {
    typingEl.classList.remove('hidden');
    msgArea.scrollTop = msgArea.scrollHeight;
  }
});

socket.on('stop_typing', () => typingEl.classList.add('hidden'));

// scroll to bottom on load
msgArea.scrollTop = msgArea.scrollHeight;
