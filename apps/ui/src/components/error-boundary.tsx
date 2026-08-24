'use client';

import { Component, type ErrorInfo, type ReactNode } from 'react';

/**
 * A boundary small enough to contain one message rather than the page.
 *
 * The route-level `error.tsx` catches everything eventually, but losing the
 * whole thread to one malformed part is a poor trade during a live run: the
 * answer above it is often what the user wanted. This degrades the offending
 * message instead and leaves the rest of the conversation on screen.
 *
 * A class is the only way to catch a render throw -- React exposes no hook.
 */
export class ErrorBoundary extends Component<
  { children: ReactNode; fallback: ReactNode; label?: string },
  { hasError: boolean }
> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(
      `${this.props.label ?? 'ErrorBoundary'} caught:`,
      error,
      info.componentStack,
    );
  }

  render() {
    return this.state.hasError ? this.props.fallback : this.props.children;
  }
}
