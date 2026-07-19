import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = {
  children: ReactNode;
  onReset?: () => void;
  onBackToOverview?: () => void;
};

type State = {
  hasError: boolean;
  message: string;
};

export class JourneyDetailErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, message: "" };

  static getDerivedStateFromError(error: Error): State {
    return {
      hasError: true,
      message: error?.message || "render_error",
    };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    if (import.meta.env.DEV) {
      console.error("[journey-detail]", error, info.componentStack);
    }
  }

  private reset = () => {
    this.setState({ hasError: false, message: "" });
    this.props.onReset?.();
  };

  render() {
    if (!this.state.hasError) return this.props.children;

    return (
      <div className="journey-detail-error" data-testid="journey-detail-error">
        <p>该Scene的部分分析内容无法显示。</p>
        {import.meta.env.DEV ? (
          <p className="journey-detail-error-dev">{this.state.message}</p>
        ) : null}
        <div className="journey-detail-error-actions">
          <button type="button" data-testid="journey-detail-error-close" onClick={this.reset}>
            收起详情
          </button>
          <button
            type="button"
            data-testid="journey-detail-error-overview"
            onClick={() => {
              this.reset();
              this.props.onBackToOverview?.();
            }}
          >
            返回旅程总览
          </button>
          <button
            type="button"
            data-testid="journey-detail-error-reload"
            onClick={() => window.location.reload()}
          >
            重新加载结果
          </button>
        </div>
      </div>
    );
  }
}
