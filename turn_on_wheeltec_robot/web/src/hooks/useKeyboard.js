import { useEffect, useRef } from 'react';

export function useKeyboard(dispatch, stopFn) {
  const keyRef = useRef({});

  useEffect(() => {
    function sync() {
      const k = keyRef.current;
      const fwd = k.w || k.arrowup;
      const bwd = k.s || k.arrowdown;
      const left = k.a || k.arrowleft;
      const right = k.d || k.arrowright;
      dispatch({ type: 'SET_STICK', value: { x: (right ? 1 : 0) - (left ? 1 : 0), y: (bwd ? 1 : 0) - (fwd ? 1 : 0) } });
      dispatch({ type: 'SET_LATERAL', value: (k.e ? 1 : 0) - (k.q ? 1 : 0) });
      dispatch({ type: 'SET_MULT', value: k.shift ? 1.5 : 1 });
    }

    const allowed = ['w', 'a', 's', 'd', 'q', 'e', 'arrowup', 'arrowdown', 'arrowleft', 'arrowright', 'shift'];

    function down(e) {
      const key = e.key === ' ' ? 'space' : e.key.toLowerCase();
      if (allowed.includes(key)) {
        e.preventDefault();
        keyRef.current[key] = true;
        sync();
      }
      if (key === 'space' && stopFn) stopFn();
    }

    function up(e) {
      const key = e.key === ' ' ? 'space' : e.key.toLowerCase();
      keyRef.current[key] = false;
      sync();
    }

    window.addEventListener('keydown', down);
    window.addEventListener('keyup', up);
    return () => {
      window.removeEventListener('keydown', down);
      window.removeEventListener('keyup', up);
    };
  }, [dispatch, stopFn]);
}
