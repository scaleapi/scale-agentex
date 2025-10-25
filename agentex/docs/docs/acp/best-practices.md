# Best Practices

Guidelines for building robust, maintainable, and secure agents with ACP.

## General Guidelines

- **Start simple** - Begin with Sync ACP unless you have specific needs for Agentic
- **Type safety** - Always use proper type annotations and parameter validation
- **Error handling** - Implement comprehensive error handling for production
- **Testing** - Test both happy path and error scenarios
- **Documentation** - Document your agent's behavior and expected inputs

## Performance

- **Async operations** - Use `await` for all ADK operations
- **Efficient state access** - Batch state operations when possible
- **Resource cleanup** - Always clean up resources in Agentic ACP
- **Caching** - Cache expensive operations when appropriate

## Security

- **Input validation** - Validate all incoming parameters
- **Error messages** - Don't leak sensitive information
- **State isolation** - Ensure proper task/agent state isolation
- **Authentication** - Implement proper authentication when needed

---

## Next Steps

- **New to ACP?** Follow the [Quick Start Guide on GitHub](https://github.com/scaleapi/scale-agentex#quick-start)
- **Ready to build?** Check out [Tutorials on GitHub](https://github.com/scaleapi/scale-agentex-python/tree/main/examples/tutorials)
- **Need help choosing?** Read [Developing Agentex Agents](../developing_agentex_agents.md)
