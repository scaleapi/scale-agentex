import { cva } from "class-variance-authority";

type Props = {
  size?:
    | "xs"
    | "sm"
    | "md"
    | "lg"
    | "xl"
    | "2xl"
    | "3xl"
    | "4xl"
    | "5xl"
    | "6xl"
    | "7xl"
    | "8xl"
    | "9xl";
};

const loadingOrbStyles = cva("", {
  variants: {
    size: {
      xs: "size-4",
      sm: "size-5",
      md: "size-6",
      lg: "size-7",
      xl: "size-8",
      "2xl": "size-9",
      "3xl": "size-10",
      "4xl": "size-11",
      "5xl": "size-12",
      "6xl": "size-15",
      "7xl": "size-18",
      "8xl": "size-24",
      "9xl": "size-32",
    },
  },
  defaultVariants: {
    size: "md",
  },
});

/**
 * Download these assets and put them in your own /public/assets directory on your website
 * to use this component.
 *
 * - loading-orb.webm from http://localhost:3000/assets/loading-orb.webm
 * - loading-orb.mp4 from http://localhost:3000/assets/loading-orb.mp4
 */
export function LoadingOrb({ size }: Props) {
  return (
    <video
      autoPlay
      loop
      muted
      playsInline
      preload="auto"
      aria-label="Loading animation"
      className={loadingOrbStyles({ size })}
    >
      <source src="/assets/loading-orb.mp4" type="video/mp4; codecs=hvc1" />
      <source src="/assets/loading-orb.webm" type="video/webm; codecs=vp9" />
    </video>
  );
}
