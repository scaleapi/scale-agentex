# Webhook Concepts

Webhooks allow you to add your own custom routes to your agent to handle external events that are not part of the standard agent lifecycle (like `on_task_create`, `on_message_send`, or `on_task_event_send`). This way, your agent can respond to events outside of the Agentex ecosystem. Read below to learn more about how to integrate agents with webhooks.

**Use webhooks when you need to:**

- Respond to external system events (GitHub pushes, Slack messages, payment notifications, etc.)
- Integrate with third-party services that send HTTP callbacks
- Handle custom endpoints that don't fit the standard ACP protocol

## Agent Changes

For each event type that you would like the agent to handle, decide on a unique URL path that these events will be forwarded to and whether this will be done via a GET or POST request.
As an example, suppose we decide to handle code change events as POST requests to the `/code_changes` endpoint.
The code below will allow the agent to receive the POST requests and handle them appropriately:

```python
@acp.post("/code_changes")
async def handle_code_changes(request: Request) -> JSONResponse:
    # Handle the code changes here
    ...
    # Return a response if desired
    return JSONResponse(content={"message": "Success"})
```

As you can see above, the handler function has access to the full request sent to the agent, including the relevant headers and the payload body if one exists.

**Common Use Case - Routing to ACP:**

A common pattern is to receive the webhook, process the custom JSON payload from the external provider, and then route it to your agent via an ACP-compatible message to the correct task:

```python
@acp.post("/code_changes")
async def handle_code_changes(request: Request) -> JSONResponse:
    # Parse the webhook payload
    payload = await request.json()
    
    # Extract relevant information
    pr_number = payload.get("pull_request", {}).get("number")
    commit_message = payload.get("commits", [{}])[0].get("message")
    
    # Find or create the appropriate task for this PR
    task_id = await get_or_create_task_for_pr(pr_number)
    
    # Route to your agent via ACP by sending an event
    await adk.events.send_event(
        task_id=task_id,
        agent_id=params.agent.id,
        content=TextContent(
            author=MessageAuthor.USER,
            content=f"Code change detected: {commit_message}"
        )
    )
    
    return JSONResponse(content={"message": "Success"})
```

This allows you to bridge external systems with your agent's standard lifecycle handlers.

Once all the desired event handlers are added to the agent implementation, and the agent is (re)deployed, the defined routes will be accessible as described below.

## Accessing Routes

To check that the route above has been correctly registered, you should be able to send a POST (or GET, as appropriate) request to `/agents/forward/name/AGENT_NAME/code_changes`.
If a 404 Not Found response is returned, please confirm that the correct agent name is provided and that the URL path after the agent name matches exactly the route defined for the handler.
Otherwise, you will receive an Unauthorized response as this route is available but protected to prevent spurious or malicious requests from tainting the agent state and lifecycle.
Please read below to learn more about how Agent API Keys are used to help authenticate these forward requests.

## API Keys

The forward routes described above rely on Agent API Keys to authenticate the requests and prevent unauthorized access.
For event providers that allow custom headers to be included with their requests, please create a new key for the agent (see below) and include its value as the `x-agent-api-key` header.
At request time, the backend will verify both that this key still exists and is associated with the agent that is handling the request before passing it through to the handler implementation.

Not everyone supports including custom headers when sending webhook events - a common alternative is a configured secret which is used to sign these requests which can then be confirmed by the backend.
The way the signature is calculated differs from product to product - we have implemented this for GitHub and Slack as the two most common use cases, but please let us know if you have another use case which require custom logic.

### Creating API Keys

For now, API key management needs to be done by sending the right requests - cURL examples are given below.
For configuring API keys in the local environment, it is sufficient to access `localhost:5003` without any authentication.
To configure the API keys in a deployed environment like `https://chat.sgp.scale.com/`, you will need to make requests to `https://agentex.sgp.scale.com/` with your SGP credentials.
To get your SGP credentials, you can navigate to `https://app.sgp.scale.com/admin/api-key`, view the SGP API Key shown there and pick the appropriate Account ID from the Accounts tab.


### Viewing API Keys
You can always check to see all of the existing API keys that have been configured for a given agent by running the following command:
```bash
# local 
curl http://localhost:5003/agent_api_keys?agent_name=AGENT_NAME
# remote
curl https://agentex.sgp.scale.com/agent_api_keys?agent_name=AGENT_NAME \
  -H "x-api-key: <SGP API KEY>" \
  -H "x-selected-account-id: <SGP ACCOUNT ID>"
```

Note that this will not show you the values of the configured API keys (by design).
The examples below will just use $HOST instead of the local or remote version - please remember to attach the API key and Account ID headers if you're not doing local development!

#### General

To create an API key that will be included as the `x-agent-api-key` header, pick a memorable name for it (these will be unique per agent) and run the following command:
```bash
curl -X POST $HOST/agent_api_keys \
  -H "Content-Type: application/json" \
  -d '{
    "agent_name": "<AGENT_NAME>",
    "name": "mysecretkey"
  }'
```

The backend will generate an API key value for you, store this in the database, and return the value for you in the response so that you can set it appropriately.
You will not be able to retrieve the API key value after you've created the API key so keep it in a safe place!

#### GitHub

To store a GitHub secret that will be used to verify incoming webhook requests, grab the full name of the repository you will be configuring the webhook for and run the following command:
```bash
# Replace with your repository name instead of scaleapi/agentex!
curl -X POST $HOST/agent_api_keys \
  -H "Content-Type: application/json" \
  -d '{
    "agent_name": "<AGENT_NAME>",
    "name": "scaleapi/agentex",
    "api_key_type": "github"
  }'
```
The backend will generate an API key value for you, store this in the database, and return the value for you in the response so that you can set it in GitHub as the webhook secret.
If you already have a webhook configured with a secret and you don't want to rotate it, you can also pass it as follows:
```bash
# Replace with your repository name instead of scaleapi/agentex
curl -X POST $HOST/agent_api_keys \
  -H "Content-Type: application/json" \
  -d '{
    "agent_name": "<AGENT_NAME>",
    "name": "scaleapi/agentex",
    "api_key_type": "github",
    "api_key": "existingsecret"
  }'
```

#### Slack
To store a Slack secret that will be used to verify incoming webhook requests, you will need:
- the App ID you will be configuring the webhook for (you can find this under Your Apps at https://api.slack.com/apps/)
- the Signing Secret, available in the app admin panel under Basic Info

If these are, for example, `A123ABC456` and `abcdefg12345` respectively, then run the following command:
```bash
curl -X POST $HOST/agent_api_keys \
  -H "Content-Type: application/json" \
  -d '{
    "agent_name": "<AGENT_NAME>",
    "name": "A123ABC456",
    "api_key_type": "slack",
    "api_key": "abcdefg12345"
  }'
```

### Deleting API Keys
If you'd like to remove an existing API key for whatever reason, first grab its ID by listing the keys for the appropriate agent as above.
Once you have it, just send the following command:
```bash
curl -X DELETE $HOST/agent_api_keys/API_KEY_ID
```
and the key will be removed, allowing you to make a new one with the same name if desired.