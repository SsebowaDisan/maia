import { Component, type ErrorInfo, type ReactNode } from "react";

type WidgetRenderBoundaryProps = {
  children: ReactNode;
  fallback?: ReactNode;
};

type WidgetRenderBoundaryState = {
  hasError: boolean;
};

class WidgetRenderBoundary extends Component<
  WidgetRenderBoundaryProps,
  WidgetRenderBoundaryState
> {
  state: WidgetRenderBoundaryState = {
    hasError: false,
  };

  static getDerivedStateFromError(): WidgetRenderBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(_error: Error, _errorInfo: ErrorInfo) {
    // Keep rendering isolated to the failed widget block.
  }

  render() {
    if (this.state.hasError) {
      return (
        this.props.fallback || (
          <div className="rounded-2xl border border-[#fecaca] bg-[#fff1f2] px-4 py-3 text-[12px] text-[#9f1239]">
            This widget failed to render.
          </div>
        )
      );
    }
    return this.props.children;
  }
}

export { WidgetRenderBoundary };
