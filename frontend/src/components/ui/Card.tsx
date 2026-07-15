import React from 'react';
import clsx from 'clsx';

interface CardProps {
  title?:     string;
  subtitle?:  string;
  children:   React.ReactNode;
  className?: string;
  icon?:      React.ReactNode;
  gradient?:  boolean;
  action?:    React.ReactNode;
}

export default function Card({ title, subtitle, children, className, icon, gradient = false, action }: CardProps) {
  return (
    <div
      className={clsx(
        'relative rounded-2xl border border-white/8 backdrop-blur-sm',
        'bg-gradient-to-br from-slate-900/80 to-slate-800/60',
        'shadow-card hover:shadow-card-hover transition-shadow duration-300',
        gradient && 'before:absolute before:inset-0 before:rounded-2xl before:p-px before:bg-gradient-to-br before:from-primary-600/40 before:via-transparent before:to-accent-500/40 before:-z-10',
        className,
      )}
    >
      {/* Optional gradient top border */}
      {gradient && (
        <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-primary-500/60 to-transparent rounded-t-2xl" />
      )}

      {(title || icon || action) && (
        <div className="flex items-center justify-between px-5 pt-4 pb-2">
          <div className="flex items-center gap-2.5">
            {icon && (
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-600/20 text-primary-400">
                {icon}
              </div>
            )}
            <div>
              {title && (
                <h3 className="text-sm font-semibold text-white tracking-wide">{title}</h3>
              )}
              {subtitle && (
                <p className="text-xs text-slate-400 mt-0.5">{subtitle}</p>
              )}
            </div>
          </div>
          {action && <div>{action}</div>}
        </div>
      )}

      <div className={clsx((title || icon) && 'px-5 pb-5 pt-2', !title && !icon && 'p-5')}>
        {children}
      </div>
    </div>
  );
}
