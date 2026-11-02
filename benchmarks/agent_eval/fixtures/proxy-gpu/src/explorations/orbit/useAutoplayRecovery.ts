import { useEffect, useRef } from 'react';

/** Retry denied playback only inside a real gesture, without stealing media controls. */
export function useAutoplayRecovery(
  enabled: boolean,
  blocked: boolean,
  play: () => Promise<boolean>,
) {
  const pending = useRef(false);
  useEffect(() => {
    if (!enabled || !blocked) return;
    const recover = (event: MouseEvent | KeyboardEvent) => {
      if (
        !event.isTrusted ||
        pending.current ||
        document.visibilityState !== 'visible'
      )
        return;
      if (event instanceof KeyboardEvent && !['Enter', ' '].includes(event.key))
        return;
      if (
        (event.target as Element | null)?.closest(
          'a, button, input, select, textarea, [contenteditable]',
        )
      )
        return;
      pending.current = true;
      // Invoke before yielding: WebKit requires play() in the gesture's stack.
      void play().finally(() => {
        pending.current = false;
      });
    };
    window.addEventListener('click', recover);
    window.addEventListener('keydown', recover);
    return () => {
      window.removeEventListener('click', recover);
      window.removeEventListener('keydown', recover);
    };
  }, [enabled, blocked, play]);
}
