// Mermaid diagram loader
// This file initializes Mermaid and renders all diagrams on the page

(function() {
  'use strict';

  // Wait for DOM to fully load
  document.addEventListener("DOMContentLoaded", function() {
    // Check if Mermaid is loaded
    if (typeof mermaid === 'undefined') {
      console.error('Mermaid library not loaded');
      return;
    }

    // Initialize Mermaid with configuration
    const config = window.mermaidConfig || {
      startOnLoad: false,
      theme: "default"
    };

    mermaid.initialize(config);

    // Find all Mermaid diagram blocks
    // MkDocs + pymdownx.superfences creates: <pre class="mermaid"><code>...</code></pre>
    const diagramBlocks = document.querySelectorAll('pre.mermaid, pre code.mermaid');

    if (diagramBlocks.length === 0) {
      return; // No diagrams on this page
    }

    // Render each diagram
    diagramBlocks.forEach((block, index) => {
      try {
        // Get the diagram code
        let diagramCode;
        if (block.tagName === 'CODE') {
          // If it's a <code> element, get its text
          diagramCode = block.textContent;
          block = block.parentElement; // Move to the <pre> element
        } else {
          // If it's a <pre> element, check for <code> inside
          const codeElement = block.querySelector('code');
          diagramCode = codeElement ? codeElement.textContent : block.textContent;
        }

        // Create a unique ID for this diagram
        const diagramId = `mermaid-diagram-${index}-${Date.now()}`;

        // Create a container for the rendered diagram
        const container = document.createElement('div');
        container.className = 'mermaid-container';
        container.style.textAlign = 'center';
        container.style.margin = '1em 0';

        // Render the diagram
        mermaid.render(diagramId, diagramCode).then(result => {
          container.innerHTML = result.svg;

          // Replace the original code block with the rendered diagram
          if (block.parentNode) {
            block.parentNode.replaceChild(container, block);
          }
        }).catch(error => {
          console.error(`Error rendering Mermaid diagram ${index}:`, error);
          // Keep the original block if rendering fails
        });
      } catch (error) {
        console.error(`Error processing Mermaid diagram ${index}:`, error);
      }
    });
  });
})();
