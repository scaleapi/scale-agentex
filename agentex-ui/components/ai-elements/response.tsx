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
      className="text-primary-foreground font-medium wrap-anywhere underline"
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
