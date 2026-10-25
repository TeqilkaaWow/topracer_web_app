// Регистрация Service Worker
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js')
    .then(reg => console.log('SW зарегистрирован:', reg.scope))
    .catch(err => console.error('SW ошибка:', err));
}

// Запрос разрешения на Push
async function requestPushPermission() {
  if (!('Notification' in window)) return false;
  if (Notification.permission === 'granted') return true;
  if (Notification.permission === 'denied') return false;

  const permission = await Notification.requestPermission();
  return permission === 'granted';
}

// Подписка на Push (сохранение subscription на сервер)
async function subscribePush() {
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) return;

  const reg = await navigator.serviceWorker.ready;
  const subscription = await reg.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array('ВАШ_VAPID_PUBLIC_KEY')
  });

  await fetch('/api/push/subscribe', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(subscription)
  });
}

function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - base64String.length % 4) % 4);
  const base64 = (base64String + padding).replace(/\-/g, '+').replace(/_/g, '/');
  const rawData = window.atob(base64);
  return Uint8Array.from([...rawData].map(char => char.charCodeAt(0)));
}

// Авто-подписка после входа
document.addEventListener('DOMContentLoaded', () => {
  if (Notification.permission === 'default') {
    setTimeout(() => {
      if (confirm('🔔 Разрешить уведомления от TopRace Z7?')) {
        requestPushPermission().then(granted => {
          if (granted) subscribePush();
        });
      }
    }, 3000);
  }
});