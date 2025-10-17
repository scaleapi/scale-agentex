import { cn } from "@/lib/utils";
import type { Task } from "agentex/resources";

interface TaskStatusIconProps {
  status: Task["status"];
  className?: string | undefined;
}

const SuccessIcon = ({ className }: { className?: string | undefined }) => (
  <svg
    width="12"
    height="12"
    viewBox="0 0 12 12"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
  >
    <g clipPath="url(#clip0_853_17376)">
      <path
        d="M6 0C2.691 0 0 2.691 0 6C0 9.309 2.691 12 6 12C9.309 12 12 9.309 12 6C12 2.691 9.309 0 6 0ZM8.853 4.45L5.85 8.45C5.72 8.624 5.521 8.732 5.304 8.748C5.285 8.749 5.268 8.75 5.25 8.75C5.052 8.75 4.861 8.672 4.72 8.531L3.217 7.031C2.924 6.739 2.924 6.263 3.217 5.97C3.51 5.677 3.985 5.676 4.279 5.97L5.171 6.86L7.655 3.55C7.903 3.219 8.373 3.15 8.705 3.401C9.036 3.65 9.103 4.12 8.854 4.451L8.853 4.45Z"
        fill="#6B7280"
      />
    </g>
    <defs>
      <clipPath id="clip0_853_17376">
        <rect width="12" height="12" fill="white" />
      </clipPath>
    </defs>
  </svg>
);

const FailedIcon = ({ className }: { className?: string | undefined }) => (
  <svg
    width="12"
    height="12"
    viewBox="0 0 12 12"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
  >
    <g clipPath="url(#clip0_853_17383)">
      <path
        d="M6 0C2.691 0 0 2.691 0 6C0 9.309 2.691 12 6 12C9.309 12 12 9.309 12 6C12 2.691 9.309 0 6 0ZM5.25 3.5C5.25 3.086 5.586 2.75 6 2.75C6.414 2.75 6.75 3.086 6.75 3.5V6.5C6.75 6.914 6.414 7.25 6 7.25C5.586 7.25 5.25 6.914 5.25 6.5V3.5ZM6 9.75C5.518 9.75 5.125 9.357 5.125 8.875C5.125 8.393 5.518 8 6 8C6.482 8 6.875 8.393 6.875 8.875C6.875 9.357 6.482 9.75 6 9.75Z"
        fill="#EF4444"
      />
    </g>
    <defs>
      <clipPath id="clip0_853_17383">
        <rect width="12" height="12" fill="white" />
      </clipPath>
    </defs>
  </svg>
);

const ErrorIcon = ({ className }: { className?: string | undefined }) => (
  <svg
    width="12"
    height="12"
    viewBox="0 0 12 12"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
  >
    <g clipPath="url(#clip0_853_17390)">
      <path
        d="M6 0C2.691 0 0 2.691 0 6C0 9.309 2.691 12 6 12C9.309 12 12 9.309 12 6C12 2.691 9.309 0 6 0ZM8.53 7.47C8.823 7.763 8.823 8.238 8.53 8.531C8.384 8.677 8.192 8.751 8 8.751C7.808 8.751 7.616 8.678 7.47 8.531L6 7.061L4.53 8.531C4.384 8.677 4.192 8.751 4 8.751C3.808 8.751 3.616 8.678 3.47 8.531C3.177 8.238 3.177 7.763 3.47 7.47L4.94 6L3.47 4.53C3.177 4.237 3.177 3.762 3.47 3.469C3.763 3.176 4.238 3.176 4.531 3.469L6.001 4.939L7.471 3.469C7.764 3.176 8.239 3.176 8.532 3.469C8.825 3.762 8.825 4.237 8.532 4.53L7.062 6L8.532 7.47H8.53Z"
        fill="#EF4444"
      />
    </g>
    <defs>
      <clipPath id="clip0_853_17390">
        <rect width="12" height="12" fill="white" />
      </clipPath>
    </defs>
  </svg>
);

const CanceledIcon = ({ className }: { className?: string | undefined }) => (
  <svg
    width="12"
    height="12"
    viewBox="0 0 12 12"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
  >
    <g clipPath="url(#clip0_853_17390_gray)">
      <path
        d="M6 0C2.691 0 0 2.691 0 6C0 9.309 2.691 12 6 12C9.309 12 12 9.309 12 6C12 2.691 9.309 0 6 0ZM8.53 7.47C8.823 7.763 8.823 8.238 8.53 8.531C8.384 8.677 8.192 8.751 8 8.751C7.808 8.751 7.616 8.678 7.47 8.531L6 7.061L4.53 8.531C4.384 8.677 4.192 8.751 4 8.751C3.808 8.751 3.616 8.678 3.47 8.531C3.177 8.238 3.177 7.763 3.47 7.47L4.94 6L3.47 4.53C3.177 4.237 3.177 3.762 3.47 3.469C3.763 3.176 4.238 3.176 4.531 3.469L6.001 4.939L7.471 3.469C7.764 3.176 8.239 3.176 8.532 3.469C8.825 3.762 8.825 4.237 8.532 4.53L7.062 6L8.532 7.47H8.53Z"
        fill="#6B7280"
      />
    </g>
    <defs>
      <clipPath id="clip0_853_17390_gray">
        <rect width="12" height="12" fill="white" />
      </clipPath>
    </defs>
  </svg>
);

const LoadingIcon = ({ className }: { className?: string | undefined }) => (
  <svg
    width="12"
    height="12"
    viewBox="0 0 12 12"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={cn("animate-spin", className)}
  >
    <g clipPath="url(#clip0_853_17362)">
      <path
        d="M6.00012 3.33366C5.72412 3.33366 5.50012 3.10966 5.50012 2.83366V1.16699C5.50012 0.890992 5.72412 0.666992 6.00012 0.666992C6.27612 0.666992 6.50012 0.890992 6.50012 1.16699V2.83366C6.50012 3.10966 6.27612 3.33366 6.00012 3.33366Z"
        fill="#6B7280"
      />
      <path
        opacity="0.88"
        d="M8.23946 4.26023C8.11146 4.26023 7.98346 4.21158 7.88612 4.11358C7.69079 3.91825 7.69079 3.60156 7.88612 3.40623L9.06479 2.22755C9.26012 2.03222 9.57679 2.03222 9.77212 2.22755C9.96746 2.42289 9.96746 2.73958 9.77212 2.93491L8.59346 4.11358C8.49612 4.21091 8.36746 4.26023 8.23946 4.26023Z"
        fill="#6B7280"
      />
      <path
        opacity="0.75"
        d="M10.8334 6.5H9.16675C8.89075 6.5 8.66675 6.276 8.66675 6C8.66675 5.724 8.89075 5.5 9.16675 5.5H10.8334C11.1094 5.5 11.3334 5.724 11.3334 6C11.3334 6.276 11.1094 6.5 10.8334 6.5Z"
        fill="#6B7280"
      />
      <path
        opacity="0.63"
        d="M9.41739 9.91745C9.28939 9.91745 9.16139 9.86878 9.06406 9.77078L7.88539 8.59211C7.69006 8.39678 7.69006 8.08011 7.88539 7.88478C8.08072 7.68945 8.39739 7.68945 8.59272 7.88478L9.77139 9.06345C9.96672 9.25878 9.96672 9.57545 9.77139 9.77078C9.67406 9.86811 9.54606 9.91745 9.41806 9.91745H9.41739Z"
        fill="#6B7280"
      />
      <path
        opacity="0.5"
        d="M6.00012 11.3337C5.72412 11.3337 5.50012 11.1097 5.50012 10.8337V9.16699C5.50012 8.89099 5.72412 8.66699 6.00012 8.66699C6.27612 8.66699 6.50012 8.89099 6.50012 9.16699V10.8337C6.50012 11.1097 6.27612 11.3337 6.00012 11.3337Z"
        fill="#6B7280"
      />
      <path
        opacity="0.38"
        d="M2.58272 9.91745C2.45472 9.91745 2.32672 9.86878 2.22939 9.77078C2.03405 9.57545 2.03405 9.25878 2.22939 9.06345L3.40805 7.88478C3.60339 7.68945 3.92005 7.68945 4.11538 7.88478C4.31071 8.08011 4.31071 8.39678 4.11538 8.59211L2.93672 9.77078C2.83939 9.86811 2.71139 9.91745 2.58339 9.91745H2.58272Z"
        fill="#6B7280"
      />
      <path
        opacity="0.25"
        d="M2.83341 6.5H1.16675C0.890748 6.5 0.666748 6.276 0.666748 6C0.666748 5.724 0.890748 5.5 1.16675 5.5H2.83341C3.10941 5.5 3.33341 5.724 3.33341 6C3.33341 6.276 3.10941 6.5 2.83341 6.5Z"
        fill="#6B7280"
      />
      <path
        opacity="0.13"
        d="M3.76078 4.26023C3.63278 4.26023 3.50478 4.21158 3.40745 4.11358L2.22878 2.93491C2.03344 2.73958 2.03344 2.42289 2.22878 2.22755C2.42411 2.03222 2.74078 2.03222 2.93612 2.22755L4.11478 3.40623C4.31012 3.60156 4.31012 3.91825 4.11478 4.11358C4.01745 4.21091 3.88878 4.26023 3.76078 4.26023Z"
        fill="#6B7280"
      />
    </g>
    <defs>
      <clipPath id="clip0_853_17362">
        <rect width="12" height="12" fill="white" />
      </clipPath>
    </defs>
  </svg>
);

export function TaskStatusIcon({ status, className }: TaskStatusIconProps) {
  switch (status) {
    case "COMPLETED":
      return <SuccessIcon className={className} />;
    case "FAILED":
    case "TIMED_OUT":
      return <FailedIcon className={className} />;
    case "CANCELED":
    case "TERMINATED":
      return <CanceledIcon className={className} />;
    case "RUNNING":
      return <LoadingIcon className={className} />;
    default:
      status satisfies null | undefined;
      return null;
  }
}

export { CanceledIcon, ErrorIcon, FailedIcon, LoadingIcon, SuccessIcon };

