import { motion } from 'framer-motion';

/**
 * The number of seconds between each shimmer
 */
const SHIMMER_DELAY = 0.05;

type ShimmeringTextProps = {
  text: string;
  enabled?: boolean;
};

export const ShimmeringText = ({
  text,
  enabled = true,
}: ShimmeringTextProps) => {
  const characters = [...text];

  if (!enabled) {
    return text;
  }

  return (
    <div className="relative">
      {characters.map((char, index) => (
        <motion.span
          key={index}
          animate={{
            color: ['rgb(55 65 81)', 'rgb(220, 220, 220)', 'rgb(55 65 81)'],
          }}
          transition={{
            delay: index * 0.02,
            duration: text.length * 0.02,
            repeat: Infinity,
            repeatDelay: characters.length * 0.02 + SHIMMER_DELAY,
            ease: 'easeInOut',
          }}
          style={{ color: 'rgb(55 65 81)' }}
        >
          {char}
        </motion.span>
      ))}
    </div>
  );
};
