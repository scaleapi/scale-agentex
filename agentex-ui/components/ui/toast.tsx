import { toast as reactToastifyToast, ToastOptions } from 'react-toastify';

interface ToastConfig {
  title: string;
  message?: string;
  options?: ToastOptions;
}

function formatToast(title: string, message?: string) {
  if (!message) {
    return title;
  }

  return (
    <div className="flex flex-col">
      <h3 className="text-sm font-semibold">{title}</h3>
      <p className="text-sm">{message}</p>
    </div>
  );
}

export const toast = {
  error: (config: string | ToastConfig, options?: ToastOptions) => {
    if (typeof config === 'string') {
      return reactToastifyToast.error(config, options);
    }
    return reactToastifyToast.error(formatToast(config.title, config.message), {
      ...options,
      ...config.options,
    });
  },

  success: (config: string | ToastConfig, options?: ToastOptions) => {
    if (typeof config === 'string') {
      return reactToastifyToast.success(config, options);
    }
    return reactToastifyToast.success(
      formatToast(config.title, config.message),
      { ...options, ...config.options }
    );
  },

  info: (config: string | ToastConfig, options?: ToastOptions) => {
    if (typeof config === 'string') {
      return reactToastifyToast.info(config, options);
    }
    return reactToastifyToast.info(formatToast(config.title, config.message), {
      ...options,
      ...config.options,
    });
  },

  warning: (config: string | ToastConfig, options?: ToastOptions) => {
    if (typeof config === 'string') {
      return reactToastifyToast.warning(config, options);
    }
    return reactToastifyToast.warning(
      formatToast(config.title, config.message),
      { ...options, ...config.options }
    );
  },

  default: (config: string | ToastConfig, options?: ToastOptions) => {
    if (typeof config === 'string') {
      return reactToastifyToast(config, options);
    }
    return reactToastifyToast(formatToast(config.title, config.message), {
      ...options,
      ...config.options,
    });
  },
};
