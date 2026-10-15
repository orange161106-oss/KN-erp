import { Component } from 'react';
import type { ReactNode } from 'react';
import { useLocation } from 'react-router-dom';

class PageErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (this.state.failed) return <div role="alert" className="p-4">
      <p>This page could not load. Check your connection and reload the page.</p>
      <button type="button" onClick={() => window.location.reload()} className="mt-2 underline">Reload page</button>
    </div>;
    return this.props.children;
  }
}

export default function PageBoundary({ children }: { children: ReactNode }) {
  const location = useLocation();
  return <PageErrorBoundary key={location.pathname}>{children}</PageErrorBoundary>;
}
