import * as React from 'react';
import {
  type ForwardRefExoticComponent,
  type RefAttributes,
  useMemo,
} from 'react';

import { cva, type VariantProps } from 'class-variance-authority';
import { type LucideProps } from 'lucide-react';

import { Button, type ButtonProps } from '@/components/ui/button';

const iconSizeVariants = cva('', {
  variants: {
    iconSize: {
      default: 'size-5',
      sm: 'size-4',
      lg: 'size-6',
    },
  },
  defaultVariants: {
    iconSize: 'default',
  },
});

export type IconButtonProps = Omit<ButtonProps, 'size' | 'asChild'> &
  VariantProps<typeof iconSizeVariants> & {
    icon: ForwardRefExoticComponent<
      Omit<LucideProps, 'ref'> & RefAttributes<SVGSVGElement>
    >;
    label?: string;
  };

const IconButton = React.forwardRef<HTMLButtonElement, IconButtonProps>(
  ({ icon, label, iconSize, children, ...props }, ref) => {
    const Icon = useMemo(() => icon, [icon]);
    return (
      <Button ref={ref} size="icon" {...props}>
        <Icon className={iconSizeVariants({ iconSize })} />
        {label && <span className="sr-only">{label}</span>}
        {children && <span>{children}</span>}
      </Button>
    );
  }
);

IconButton.displayName = 'IconButton';

export { IconButton };
