import { Component, type ReactNode } from 'react';

export default class AppErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (this.state.failed) return <main className="page-container" role="alert">
      <h1>This page could not load</h1>
      <p>Your saved data has not been changed. Reload to try again.</p>
      <button onClick={() => window.location.reload()}>Reload application</button>{' '}
      <a href="/">Return home</a>
    </main>;
    return this.props.children;
  }
}
