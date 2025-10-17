declare module '@milkdown/crepe' {
  export class Crepe {
    static Feature: {
      BlockEdit: 'BlockEdit';
      CodeMirror: 'CodeMirror';
      ListItem: 'ListItem';
      LinkTooltip: 'LinkTooltip';
      ImageBlock: 'ImageBlock';
      Placeholder: 'Placeholder';
      Table: 'Table';
      Toolbar: 'Toolbar';
      Cursor: 'Cursor';
      Latex: 'Latex';
    };

    constructor(options: {
      root: HTMLElement;
      defaultValue?: string;
      features?: Record<string, boolean>;
      featureConfigs?: Record<string, any>;
    });

    create(): Promise<void>;
    destroy(): void;
    setReadonly(value: boolean): void;
    getMarkdown(): string;
    on(
      callback: (listener: {
        markdownUpdated: (callback: (markdown: string) => void) => void;
        updated: (callback: () => void) => void;
        focus: (callback: () => void) => void;
        blur: (callback: () => void) => void;
      }) => void
    ): void;
  }
}

declare module '@milkdown/crepe/theme/common/style.css';
declare module '@milkdown/crepe/theme/nord.css';
declare module '@milkdown/crepe/theme/frame.css';
declare module '@milkdown/crepe/theme/classic.css';
declare module '@milkdown/crepe/theme/frame-dark.css';
declare module '@milkdown/crepe/theme/classic-dark.css';
declare module '@milkdown/crepe/theme/nord-dark.css';
