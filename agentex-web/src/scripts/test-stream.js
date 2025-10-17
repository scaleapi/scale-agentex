#!/usr/bin/env node

/**
 * A simple test script to directly connect to the backend SSE stream
 * Run with: node src/scripts/test-stream.js TASK_ID
 */

// Get task ID from command line
const taskId = process.argv[2];

if (!taskId) {
  console.error('Please provide a task ID as argument');
  console.error('Usage: node test-stream.js TASK_ID');
  process.exit(1);
}

console.log(`Testing SSE stream for task: ${taskId}`);

// Direct connection to backend
const apiUrl = process.env.AGENTEX_BASE_URL || 'http://localhost:5003';
const streamUrl = `${apiUrl}/tasks/${taskId}/stream`;

console.log(`Connecting to: ${streamUrl}`);

// Use the native fetch API
fetch(streamUrl, {
  headers: {
    Accept: 'text/event-stream',
    'Cache-Control': 'no-cache',
  },
})
  .then(response => {
    console.log(`Connection established, status: ${response.status}`);

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    if (!response.body) {
      throw new Error('Response has no body');
    }

    // Set up a reader for the stream
    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    let buffer = '';

    // Read the stream
    function readStream() {
      reader
        .read()
        .then(({ done, value }) => {
          if (done) {
            console.log('Stream closed by server');
            return;
          }

          // Decode the chunk and add to buffer
          const chunk = decoder.decode(value, { stream: true });
          buffer += chunk;

          // Process complete SSE messages
          while (buffer.includes('\n\n')) {
            const [message, rest] = buffer.split('\n\n', 2);
            buffer = rest;

            // Skip empty messages and comments
            if (message && !message.startsWith(':')) {
              console.log('Received SSE message:');
              console.log(message);
              console.log('---');

              // Try to parse JSON if the message is data: {...}
              if (message.startsWith('data:')) {
                try {
                  const jsonStr = message.substring(5) ? message.substring(5).trim() : '';
                  const data = JSON.parse(jsonStr);
                  console.log('Parsed data:', data);
                } catch (e) {
                  console.log('Could not parse as JSON');
                }
              }
            }
          }

          // Continue reading
          readStream();
        })
        .catch(error => {
          console.error('Error reading stream:', error);
        });
    }

    // Start reading
    readStream();
  })
  .catch(error => {
    console.error('Error connecting to SSE stream:', error);
  });

// Handle Ctrl+C to cleanly exit
process.on('SIGINT', () => {
  console.log('Closing connection and exiting...');
  process.exit(0);
});
