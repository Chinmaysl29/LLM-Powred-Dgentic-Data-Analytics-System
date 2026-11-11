// Browser verification entry point; never imported by the application.
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { ToastProvider } from '../src/components/ui/Toast';
import { useToast } from '../src/hooks/useToast';

export function ToastControls() {
  const { addToast } = useToast();
  return <>
    <button onClick={() => addToast({ message: 'Timed fixture', variant: 'info', duration: 500 })}>Timed toast</button>
    <button onClick={() => addToast({ message: 'Persistent fixture', variant: 'info', duration: 0 })}>Persistent toast</button>
  </>;
}

createRoot(document.getElementById('root')!).render(
  <StrictMode><ToastProvider><ToastControls /></ToastProvider></StrictMode>,
);
