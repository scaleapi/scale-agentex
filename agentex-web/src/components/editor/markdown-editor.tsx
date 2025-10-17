'use client';

import {FC, useEffect, useRef, useState} from 'react';
import {Crepe} from '@milkdown/crepe';
import '@milkdown/crepe/theme/common/style.css';
import '@milkdown/crepe/theme/nord.css';
import styles from './milkdown.module.css';

interface EditorProps {
  markdown: string;
  readOnly?: boolean;
  onChange?: (markdown: string) => void;
  className?: string;
  onReady?: (ready: boolean) => void;
}

const DEFAULT_FEATURES = {
  [Crepe.Feature.BlockEdit]: false, // Disable block handle and menu
};

/**
 * A Markdown editor component using Milkdown Crepe
 */
const MarkdownEditor: FC<EditorProps> = (props: EditorProps) => {
  const {markdown, readOnly = false, onChange, className, onReady} = props;
  const editorRef = useRef<Crepe | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [isEditorReady, setIsEditorReady] = useState(false);

  // Initialize the editor
  useEffect(() => {
    if (!containerRef.current) return;

    // Create the Crepe editor with disabled block handle
    const crepe = new Crepe({
      root: containerRef.current,
      defaultValue: markdown,
      features: DEFAULT_FEATURES,
    });

    editorRef.current = crepe;

    // Create the editor
    crepe.create().then(() => {
      // Set readonly mode if needed
      if (readOnly) {
        crepe.setReadonly(true);
      }

      // Add listener for markdown updates
      if (onChange) {
        crepe.on(listener => {
          listener.markdownUpdated(markdown => {
            onChange(markdown);
          });
        });
      }

      // Mark editor as ready
      setIsEditorReady(true);
      onReady?.(true);
    });

    // Cleanup function
    return () => {
      if (editorRef.current) {
        editorRef.current.destroy();
        editorRef.current = null;
      }
      setIsEditorReady(false);
      onReady?.(false);
    };
  }, []);

  // Track the last markdown to avoid unnecessary updates
  const lastMarkdownRef = useRef<string>('');

  // Update editor content when markdown prop changes
  useEffect(() => {
    // Only update if the editor is ready, we have a reference, and content actually changed
    if (
      isEditorReady &&
      editorRef.current &&
      markdown !== undefined &&
      markdown !== lastMarkdownRef.current
    ) {
      lastMarkdownRef.current = markdown;

      const updateEditor = (retryCount = 0) => {
        if (!editorRef.current || !containerRef.current) return;

        try {
          editorRef.current.destroy();
        } catch (error) {
          console.warn('Error destroying editor:', error);
        }

        onReady?.(false);

        const crepe = new Crepe({
          root: containerRef.current,
          defaultValue: markdown,
          features: DEFAULT_FEATURES,
        });

        editorRef.current = crepe;

        // Handle both sync and async errors from crepe.create()
        crepe
          .create()
          .then(() => {
            if (!editorRef.current) return; // Component might have unmounted

            if (readOnly) {
              crepe.setReadonly(true);
            }

            if (onChange) {
              crepe.on(listener => {
                listener.markdownUpdated(markdown => {
                  onChange(markdown);
                });
              });
            }
            onReady?.(true);
          })
          .catch(error => {
            console.warn(`Failed to create editor (attempt ${retryCount + 1}):`, error);

            // Retry up to 3 times with exponential backoff
            if (retryCount < 3) {
              const delay = Math.pow(2, retryCount) * 100; // 100ms, 200ms, 400ms
              setTimeout(() => {
                updateEditor(retryCount + 1);
              }, delay);
            } else {
              console.error('Max retries reached, giving up on editor update');
              onReady?.(false);
            }
          });
      };

      // Debounce rapid updates
      const timeoutId = setTimeout(() => {
        updateEditor();
      }, 1);

      return () => clearTimeout(timeoutId);
    }
  }, [markdown, readOnly, onChange, isEditorReady]);

  return (
    <div className={`${styles.wrapper} ${className || ''}`}>
      <div ref={containerRef} />
    </div>
  );
};

export default MarkdownEditor;
