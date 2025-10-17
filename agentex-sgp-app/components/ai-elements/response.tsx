'use client';

import { type ComponentProps, memo } from 'react';
import { Streamdown } from 'streamdown';

type ResponseProps = ComponentProps<typeof Streamdown>;

const components = {
  a: ({
    children,
    ...props
  }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a
      className="wrap-anywhere font-medium underline text-primary-foreground"
      {...props}
    >
      {children}
    </a>
  ),
};

export const Response = memo(
  ({ className, ...props }: ResponseProps) => (
    <Streamdown
      className={className ?? ''}
      components={components}
      {...props}
    />
  ),
  (prevProps, nextProps) => prevProps.children === nextProps.children
);

Response.displayName = 'Response';
