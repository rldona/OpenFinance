/** Web Push en el navegador (OF-1302): suscribir este dispositivo con la clave pública VAPID. */

export function pushSupported(): boolean {
  return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window && window.isSecureContext
}

function keyBytes(base64Url: string): Uint8Array<ArrayBuffer> {
  const padded = base64Url.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(base64Url.length / 4) * 4, '=')
  const raw = atob(padded)
  const bytes = new Uint8Array(new ArrayBuffer(raw.length))
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i)
  return bytes
}

async function registration() {
  return navigator.serviceWorker.ready
}

/** La suscripción de este dispositivo, si ya la hay. */
export async function currentSubscription(): Promise<PushSubscription | null> {
  if (!pushSupported()) return null
  return (await registration()).pushManager.getSubscription()
}

/** Pide permiso y suscribe este dispositivo. Devuelve `null` si la persona no da permiso. */
export async function subscribeDevice(publicKey: string): Promise<PushSubscription | null> {
  if ((await Notification.requestPermission()) !== 'granted') return null
  return (await registration()).pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: keyBytes(publicKey),
  })
}

export function subscriptionKeys(sub: PushSubscription): { endpoint: string; p256dh: string; auth: string } | null {
  const json = sub.toJSON()
  const { p256dh, auth } = json.keys ?? {}
  return json.endpoint && p256dh && auth ? { endpoint: json.endpoint, p256dh, auth } : null
}
