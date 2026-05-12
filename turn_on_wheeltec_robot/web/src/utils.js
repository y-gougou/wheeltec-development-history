export const LIMITS = {
  maxLinear: 1.0,
  maxLateral: 0.65,
  maxAngular: 2.5,
  deadzone: 0.07,
  commandMs: 33,
  heartbeatMs: 250,
};

export const DIRECTIONS = [
  { label: 'Forward-left', x: 1, y: 1 },
  { label: 'Forward', x: 1, y: 0 },
  { label: 'Forward-right', x: 1, y: -1 },
  { label: 'Left', x: 0, y: 1 },
  { label: 'Stop', x: 0, y: 0 },
  { label: 'Right', x: 0, y: -1 },
  { label: 'Back-left', x: -1, y: 1 },
  { label: 'Back', x: -1, y: 0 },
  { label: 'Back-right', x: -1, y: -1 },
];

export function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

export function normalizeVector(v) {
  const len = Math.hypot(v.x, v.y);
  if (len <= 0.001) return { x: 0, y: 0 };
  return { x: v.x / len, y: v.y / len };
}

export function axis(value, deadzone = LIMITS.deadzone) {
  const mag = Math.abs(value);
  if (mag <= deadzone) return 0;
  return Math.sign(value) * Math.min(1, (mag - deadzone) / (1 - deadzone));
}

export function emptyTwist() {
  return { linear: { x: 0, y: 0, z: 0 }, angular: { x: 0, y: 0, z: 0 } };
}

export function twist(vx = 0, vy = 0, wz = 0) {
  return { linear: { x: vx, y: vy, z: 0 }, angular: { x: 0, y: 0, z: wz } };
}

export function parseCruiseStatus(text) {
  if (!text || text === 'cruise: off') {
    return { active: false, target: { vx: 0, vy: 0, wz: 0 }, actual: { vx: 0, vy: 0, wz: 0 }, raw: text || 'cruise: off' };
  }
  const m = text.match(/vx=([-0-9.]+)\(([-0-9.]+)\)\s+vy=([-0-9.]+)\(([-0-9.]+)\)\s+wz=([-0-9.]+)\(([-0-9.]+)\)/);
  if (!m) {
    return { active: text.startsWith('cruise:'), target: { vx: 0, vy: 0, wz: 0 }, actual: { vx: 0, vy: 0, wz: 0 }, raw: text };
  }
  return {
    active: true,
    target: { vx: Number(m[1]), vy: Number(m[3]), wz: Number(m[5]) },
    actual: { vx: Number(m[2]), vy: Number(m[4]), wz: Number(m[6]) },
    raw: text,
  };
}

export function parseJsonStatus(text, fallback = {}) {
  try {
    return { ...fallback, ...JSON.parse(text || '{}') };
  } catch {
    return fallback;
  }
}

export function apiUrl(path, params = {}) {
  const url = new URL(path, window.location.origin);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.set(key, value);
    }
  });
  return url.toString();
}
