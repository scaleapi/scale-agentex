# Changelog

## [0.2.0](https://github.com/scaleapi/scale-agentex/compare/v0.1.0...v0.2.0) (2026-07-01)


### Features

* **agent_api_keys:** one-call webhook-trigger setup endpoint ([#329](https://github.com/scaleapi/scale-agentex/issues/329)) ([9cc71fb](https://github.com/scaleapi/scale-agentex/commit/9cc71fb998d00e15734d0ad7be180e1e6f1dfdda))
* **agentex-ui:** grow chat input vertically for multi-line prompts ([#332](https://github.com/scaleapi/scale-agentex/issues/332)) ([8c060f1](https://github.com/scaleapi/scale-agentex/commit/8c060f158e3ab4516fe9725887a9943f56b46826))
* **retention:** strict bool env parsing + stale-RUNNING cleanup override ([#306](https://github.com/scaleapi/scale-agentex/issues/306)) ([5ad81e8](https://github.com/scaleapi/scale-agentex/commit/5ad81e8fb9f80bb6b2bfa7c6ed05afd3d59c6a59))
* **schedules:** agent run schedules (v1) ([#335](https://github.com/scaleapi/scale-agentex/issues/335)) ([6a66ad3](https://github.com/scaleapi/scale-agentex/commit/6a66ad3003c64ad49671173043108095a6fbb843))
* **task-messages:** add optional is_error to ToolResponseContent ([#331](https://github.com/scaleapi/scale-agentex/issues/331)) ([5020e96](https://github.com/scaleapi/scale-agentex/commit/5020e96f8bb689553a8b1e253c09e5750e6f80fc))
* update task configs in agentex db on turn ([#309](https://github.com/scaleapi/scale-agentex/issues/309)) ([13eea7a](https://github.com/scaleapi/scale-agentex/commit/13eea7a68b23c169bb5e51331ee47d49ac3f11f6))


### Bug Fixes

* **authz:** grant legacy agent register principal ([#325](https://github.com/scaleapi/scale-agentex/issues/325)) ([cae5f94](https://github.com/scaleapi/scale-agentex/commit/cae5f9470c03a0c14371981a78540c4d7052819d))
* **deps:** cap fastapi &lt;0.137.0 to stop OPTIONS preflight 500s ([#334](https://github.com/scaleapi/scale-agentex/issues/334)) ([acbe9e3](https://github.com/scaleapi/scale-agentex/commit/acbe9e3957ad3867a9793d1726e07141da691f47))
* **deps:** clear golden-image Trivy CRITICAL/HIGH (litellm, starlette, pyjwt, python-multipart) ([#320](https://github.com/scaleapi/scale-agentex/issues/320)) ([bfa6652](https://github.com/scaleapi/scale-agentex/commit/bfa6652b8125dcd6beee471f21ffa313c107551b))
* **schedules:** backfill agent_run_schedules deleted_at/version on early-deployed envs ([#341](https://github.com/scaleapi/scale-agentex/issues/341)) ([fc1ba55](https://github.com/scaleapi/scale-agentex/commit/fc1ba556ff12a1fc0df8aace544f690bed97b3c7))
* **schedules:** grant legacy auth for run schedules ([#344](https://github.com/scaleapi/scale-agentex/issues/344)) ([648e81c](https://github.com/scaleapi/scale-agentex/commit/648e81cf6d9513a309a9475c228eea3ab0bf7353))
* **streams:** cut SSE error-log volume and add Redis pool headroom ([#340](https://github.com/scaleapi/scale-agentex/issues/340)) ([352eaaa](https://github.com/scaleapi/scale-agentex/commit/352eaaae082ca08a576b20880333493e449da1be))
* **streams:** snapshot SSE cursor before "connected" to stop first-token drops ([#330](https://github.com/scaleapi/scale-agentex/issues/330)) ([7c2ccfd](https://github.com/scaleapi/scale-agentex/commit/7c2ccfd61376ddeaa2ae5580bae7421adea5ffd6))
* **tasks:** preserve task_metadata in combined update and forward merge_params by name ([#336](https://github.com/scaleapi/scale-agentex/issues/336)) ([8c25c64](https://github.com/scaleapi/scale-agentex/commit/8c25c6417b6d39e2fa4457cad6ff4c37f2c952db))


### Documentation

* document Redis as a required dependency ([#343](https://github.com/scaleapi/scale-agentex/issues/343)) ([4c1740b](https://github.com/scaleapi/scale-agentex/commit/4c1740bf576eacdf2f3f4251cf1c93803b16368f))
* **guides:** tracing, framework-agent, and local-sandbox guides ([#339](https://github.com/scaleapi/scale-agentex/issues/339)) ([b43e8c3](https://github.com/scaleapi/scale-agentex/commit/b43e8c3f0d6a586e1ae676793245cc004e558c48))
* **streaming:** document the unified harness surface ([#337](https://github.com/scaleapi/scale-agentex/issues/337)) ([31fd697](https://github.com/scaleapi/scale-agentex/commit/31fd6975624d4842ca9314ee6cbd17717a0e16a5))
