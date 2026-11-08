import { Component, ErrorInfo, ReactNode } from 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';

interface Props {
  children: ReactNode;
  title?: string;
  resetKey?: string | number;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ChartErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('ChartErrorBoundary caught render error:', error, errorInfo);
  }

  public componentDidUpdate(prevProps: Props) {
    if (prevProps.resetKey !== this.props.resetKey && this.state.hasError) {
      this.setState({ hasError: false, error: undefined });
    }
  }

  private handleRetry = () => {
    this.setState({ hasError: false, error: undefined });
  };

  public render() {
    if (this.state.hasError && this.props.fallback) {
      return (
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-3 text-[13px] text-[var(--accent-coral)]">
            <span className="inline-flex items-center gap-2"><AlertCircle className="w-4 h-4" />{this.props.title || 'Ошибка построения графика'}: данные показаны в табличном виде.</span>
            <button type="button" onClick={this.handleRetry} className="inline-flex items-center gap-1.5 text-[var(--accent-primary)]"><RefreshCw className="w-3.5 h-3.5" />Повторить отрисовку</button>
          </div>
          {this.props.fallback}
        </div>
      );
    }
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center h-full min-h-[220px] p-6 text-center rounded-2xl bg-[var(--bg-input)] border border-[var(--border-glass)]">
          <div className="w-10 h-10 rounded-full bg-[var(--accent-coral-subtle)] text-[var(--accent-coral)] flex items-center justify-center mb-3">
            <AlertCircle className="w-5 h-5" />
          </div>
          <span className="text-sm font-medium font-display text-[var(--text-main)]">
            {this.props.title || 'Ошибка построения графика'}
          </span>
          <p className="text-[13px] font-body text-[var(--text-secondary)] mt-1 max-w-sm leading-relaxed">
            Не удалось построить график. Обновите страницу или повторите расчет.
          </p>
          <button
            type="button"
            onClick={this.handleRetry}
            className="mt-4 inline-flex items-center gap-1.5 px-5 py-2.5 rounded-full bg-[var(--bg-card)] hover:bg-[var(--bg-card-hover)] text-[var(--text-main)] border border-[var(--border-glass)] text-[13px] font-medium transition-all"
          >
            <RefreshCw className="w-3.5 h-3.5 text-[var(--accent-primary)]" />
            <span>Повторить отрисовку</span>
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
