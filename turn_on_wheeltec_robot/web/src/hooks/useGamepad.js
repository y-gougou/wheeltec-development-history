import { useCallback, useEffect, useRef, useState } from 'react';

const DEADZONE = 0.12;

function applyDeadzone(value) {
  const abs = Math.abs(value);
  if (abs < DEADZONE) return 0;
  return Math.sign(value) * ((abs - DEADZONE) / (1 - DEADZONE));
}

export function useGamepad(onAxes, onStop, onEstop) {
  const [connected, setConnected] = useState(false);
  const [name, setName] = useState('');
  const rafRef = useRef(null);
  const pressedRef = useRef({});

  const poll = useCallback(() => {
    const pads = navigator.getGamepads ? navigator.getGamepads() : [];
    let found = false;
    for (const pad of pads) {
      if (!pad) continue;
      found = true;

      const lx = applyDeadzone(pad.axes[0] || 0);
      const ly = applyDeadzone(pad.axes[1] || 0);
      const rx = applyDeadzone(pad.axes[2] || 0);

      onAxes({ x: lx, y: ly, turn: rx });

      const a = pad.buttons[0]?.pressed;
      const b = pad.buttons[1]?.pressed;
      const prev = pressedRef.current;

      if (a && !prev.a && onStop) onStop();
      if (b && !prev.b && onEstop) onEstop();

      pressedRef.current = { a, b };
      break;
    }
    if (found !== connected) setConnected(found);
    rafRef.current = requestAnimationFrame(poll);
  }, [onAxes, onStop, onEstop, connected]);

  useEffect(() => {
    function handleConnect(e) {
      setConnected(true);
      setName(e.gamepad?.id || 'Gamepad');
    }
    function handleDisconnect() {
      setConnected(false);
      setName('');
      onAxes({ x: 0, y: 0, turn: 0 });
    }

    window.addEventListener('gamepadconnected', handleConnect);
    window.addEventListener('gamepaddisconnected', handleDisconnect);
    rafRef.current = requestAnimationFrame(poll);

    return () => {
      window.removeEventListener('gamepadconnected', handleConnect);
      window.removeEventListener('gamepaddisconnected', handleDisconnect);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [poll, onAxes]);

  return { connected, name };
}
