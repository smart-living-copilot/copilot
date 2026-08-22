import { useEffect } from 'react';

export function useLiveModeKeyboardShortcuts({
  cameraControlsDisabled,
  dismissViewer,
  inViewer,
  isCameraEnabled,
  isConnected,
  isMicrophoneMuted,
  micControlDisabled,
  setCameraEnabled,
  setMicrophoneMuted,
}: {
  cameraControlsDisabled: boolean;
  dismissViewer: () => void;
  inViewer: boolean;
  isCameraEnabled: boolean;
  isConnected: boolean;
  isMicrophoneMuted: boolean;
  micControlDisabled: boolean;
  setCameraEnabled: (enabled: boolean) => Promise<void>;
  setMicrophoneMuted: (muted: boolean) => void;
}) {
  useEffect(() => {
    if (!isConnected && !inViewer) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target;
      if (target instanceof HTMLElement) {
        const tag = target.tagName;
        if (tag === 'INPUT' || tag === 'TEXTAREA' || target.isContentEditable) {
          return;
        }
      }

      if (event.key === 'Escape' && inViewer) {
        event.preventDefault();
        dismissViewer();
        return;
      }

      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (!isConnected) return;

      const key = event.key.toLowerCase();
      if (key === 'm') {
        if (micControlDisabled) return;
        event.preventDefault();
        setMicrophoneMuted(!isMicrophoneMuted);
      } else if (key === 'v') {
        if (cameraControlsDisabled) return;
        event.preventDefault();
        void setCameraEnabled(!isCameraEnabled);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [
    cameraControlsDisabled,
    dismissViewer,
    inViewer,
    isCameraEnabled,
    isConnected,
    isMicrophoneMuted,
    micControlDisabled,
    setCameraEnabled,
    setMicrophoneMuted,
  ]);
}
