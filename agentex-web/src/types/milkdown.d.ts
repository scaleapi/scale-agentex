declare module '@milkdown/core' {
  export interface MilkdownPlugin {
    // Plugin interface
  }

  export interface Editor {
    config: (callback: (ctx: any) => void) => Editor;
    use: (plugin: () => MilkdownPlugin) => Editor;
    action: (callback: (ctx: any) => void) => void;
  }

  export const rootCtx: any;

  export const Editor: {
    make: () => Editor;
  };
}

declare module '@milkdown/react' {
  import {Editor} from '@milkdown/core';

  export function useEditor(factory: (root: HTMLElement) => Editor): {
    get: () => Editor | null;
  };
}

declare module '@milkdown/theme-nord' {
  import {MilkdownPlugin} from '@milkdown/core';
  export const nord: () => MilkdownPlugin;
}

declare module '@milkdown/preset-commonmark' {
  import {MilkdownPlugin} from '@milkdown/core';
  export const commonmark: () => MilkdownPlugin;
}

declare module '@milkdown/plugin-prism' {
  import {MilkdownPlugin} from '@milkdown/core';
  export const prism: () => MilkdownPlugin;
}
