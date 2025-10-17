import './button.css';

export interface ButtonProps {
  /** Is this the principal call to action on the page? */
  primary?: boolean | undefined;
  /** What background color to use */
  backgroundColor?: string | undefined;
  /** How large should the button be? */
  size?: 'small' | 'medium' | 'large' | undefined;
  /** Button contents */
  label: string | undefined;
  /** Optional click handler */
  onClick?: (() => void) | undefined;
}

/** Primary UI component for user interaction */
export const Button = ({
  primary = false,
  size = 'medium',
  backgroundColor,
  label,
  ...props
}: ButtonProps) => {
  const mode = primary ? 'storybook-button--primary' : 'storybook-button--secondary';
  return (
    <button
      type="button"
      className={['storybook-button', `storybook-button--${size}`, mode].join(' ')}
      {...props}
    >
      {label}
      <style jsx>{`
        button {
          background-color: ${backgroundColor};
        }
      `}</style>
    </button>
  );
};
