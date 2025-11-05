// Mermaid configuration
// This file sets up Mermaid options before the library is loaded
window.mermaidConfig = {
  startOnLoad: false,  // We'll manually trigger rendering in extra-loader.js
  theme: "default",
  flowchart: {
    htmlLabels: false,
    useMaxWidth: true
  },
  sequence: {
    useMaxWidth: true,
    noteFontWeight: "14px",
    actorFontSize: "14px",
    messageFontSize: "16px"
  },
  er: {
    useMaxWidth: true
  },
  journey: {
    useMaxWidth: true
  },
  gitGraph: {
    useMaxWidth: true
  }
};
