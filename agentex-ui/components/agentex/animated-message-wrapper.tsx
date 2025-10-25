import { motion } from 'framer-motion';

interface AnimatedMessageWrapperProps
  extends React.HTMLAttributes<HTMLDivElement> {
  messageId: string;
  hasAnimated: boolean;
}

const animationVariants = {
  initial: { opacity: 0, y: '100vh', scale: 0.5 },
  animate: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: {
      type: 'spring' as const,
      stiffness: 500,
      damping: 35,
      mass: 0.8,
    },
  },
};

function AnimatedMessageWrapper({
  children,
  messageId,
  hasAnimated,
}: AnimatedMessageWrapperProps) {
  if (hasAnimated) {
    return <>{children}</>;
  }
  return (
    <motion.div
      variants={animationVariants}
      initial="initial"
      animate="animate"
      key={messageId}
    >
      {children}
    </motion.div>
  );
}

export { AnimatedMessageWrapper };
