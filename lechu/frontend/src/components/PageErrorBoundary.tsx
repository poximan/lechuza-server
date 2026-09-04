import { Component, type ErrorInfo, type ReactNode } from "react";

export interface PageErrorBoundaryProps {
  children: ReactNode;
  className?: string;
  resetToken: string;
}

interface PageErrorBoundaryState {
  error: string | null;
}

export class PageErrorBoundary extends Component<
  PageErrorBoundaryProps,
  PageErrorBoundaryState
> {
  public override state: PageErrorBoundaryState = { error: null };

  public static getDerivedStateFromError(
    error: unknown,
  ): PageErrorBoundaryState {
    return { error: error instanceof Error ? error.message : String(error) };
  }

  public override componentDidCatch(error: unknown, info: ErrorInfo): void {
    console.error(
      "Lechu page contract failed",
      error,
      info.componentStack,
    );
  }

  public override componentDidUpdate(previous: PageErrorBoundaryProps): void {
    if (
      this.state.error !== null &&
      previous.resetToken !== this.props.resetToken
    ) {
      this.setState({ error: null });
    }
  }

  public override render(): ReactNode {
    if (this.state.error !== null) {
      return (
        <div className={this.props.className} role="alert">
          <strong>No se pudo representar la vista.</strong>
          <span>{this.state.error}</span>
        </div>
      );
    }
    return this.props.children;
  }
}
