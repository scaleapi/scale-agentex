# Changelog

## [0.2.0](https://github.com/scaleapi/scale-agentex/compare/v0.1.0...v0.2.0) (2026-07-22)


### Features

* **agent_api_keys:** one-call webhook-trigger setup endpoint ([#329](https://github.com/scaleapi/scale-agentex/issues/329)) ([9cc71fb](https://github.com/scaleapi/scale-agentex/commit/9cc71fb998d00e15734d0ad7be180e1e6f1dfdda))
* **agentex-ui:** accept RSA (RS256) private_key_jwt keys ([#367](https://github.com/scaleapi/scale-agentex/issues/367)) ([e2c8a22](https://github.com/scaleapi/scale-agentex/commit/e2c8a2250e305cb65c105126b48053b1a290da13))
* **agentex-ui:** account picker via same-origin BFF proxy ([#350](https://github.com/scaleapi/scale-agentex/issues/350)) ([0f07dc7](https://github.com/scaleapi/scale-agentex/commit/0f07dc74dbd2450e190e07ea1fc1c2d9114000de))
* **agentex-ui:** grow chat input vertically for multi-line prompts ([#332](https://github.com/scaleapi/scale-agentex/issues/332)) ([8c060f1](https://github.com/scaleapi/scale-agentex/commit/8c060f158e3ab4516fe9725887a9943f56b46826))
* **agentex-ui:** OIDC login with server-side access token ([#351](https://github.com/scaleapi/scale-agentex/issues/351)) ([824286c](https://github.com/scaleapi/scale-agentex/commit/824286ca26e8d34fa4206abbb9f04713d8485ddb))
* **agentex:** add Slack Events API url_verification endpoint ([#369](https://github.com/scaleapi/scale-agentex/issues/369)) ([d0ba8bf](https://github.com/scaleapi/scale-agentex/commit/d0ba8bf92066aaf6985b98d7014bb56de5b7e8cd))
* **agentex:** forward OIDC bearer credential for user delegation ([#363](https://github.com/scaleapi/scale-agentex/issues/363)) ([cea5963](https://github.com/scaleapi/scale-agentex/commit/cea59632d79eece18198ce700bec29f2f9baf4b2))
* **retention:** strict bool env parsing + stale-RUNNING cleanup override ([#306](https://github.com/scaleapi/scale-agentex/issues/306)) ([5ad81e8](https://github.com/scaleapi/scale-agentex/commit/5ad81e8fb9f80bb6b2bfa7c6ed05afd3d59c6a59))
* **schedules:** add exact skip and unskip actions ([#357](https://github.com/scaleapi/scale-agentex/issues/357)) ([ac88134](https://github.com/scaleapi/scale-agentex/commit/ac88134039e92166c632cf3c9e7a176107358524))
* **schedules:** agent run schedules (v1) ([#335](https://github.com/scaleapi/scale-agentex/issues/335)) ([6a66ad3](https://github.com/scaleapi/scale-agentex/commit/6a66ad3003c64ad49671173043108095a6fbb843))
* **task-messages:** add optional is_error to ToolResponseContent ([#331](https://github.com/scaleapi/scale-agentex/issues/331)) ([5020e96](https://github.com/scaleapi/scale-agentex/commit/5020e96f8bb689553a8b1e253c09e5750e6f80fc))
* **tasks:** non-terminal task/interrupt + INTERRUPTED status (AGX1-391) ([#365](https://github.com/scaleapi/scale-agentex/issues/365)) ([a92081a](https://github.com/scaleapi/scale-agentex/commit/a92081a24c0e181cdbd6836fcc880e6be4abeb24))
* **ui:** add scheduled task management ([#354](https://github.com/scaleapi/scale-agentex/issues/354)) ([0d859c2](https://github.com/scaleapi/scale-agentex/commit/0d859c2ff85d227af124abb93dc611d40ef2337e))
* update task configs in agentex db on turn ([#309](https://github.com/scaleapi/scale-agentex/issues/309)) ([13eea7a](https://github.com/scaleapi/scale-agentex/commit/13eea7a68b23c169bb5e51331ee47d49ac3f11f6))


### Bug Fixes

* **agentex-ui:** bump postcss to &gt;=8.5.10 (CVE-2026-41305) ([#360](https://github.com/scaleapi/scale-agentex/issues/360)) ([8e5159b](https://github.com/scaleapi/scale-agentex/commit/8e5159ba59662c396b023deb9fbcbef5f72ebc3b))
* **agentex-ui:** bump tar 7.5.11 -&gt; 7.5.16 (CVE-2026-53655) ([#361](https://github.com/scaleapi/scale-agentex/issues/361)) ([f8e64a1](https://github.com/scaleapi/scale-agentex/commit/f8e64a122d128d3ff1556a8d0c7b62f30de118a2))
* **agentex-ui:** bump uuid 11.1.0 -&gt; 11.1.1 (CVE-2026-41907) ([#362](https://github.com/scaleapi/scale-agentex/issues/362)) ([9edebf5](https://github.com/scaleapi/scale-agentex/commit/9edebf53385ce7dfcc8e1de1479ff87b2e590b65))
* **agentex-ui:** merge URL updates against the live URL to fix account-switch races ([#355](https://github.com/scaleapi/scale-agentex/issues/355)) ([f87e363](https://github.com/scaleapi/scale-agentex/commit/f87e3639a2e30b62c632e08aacab95a712523055))
* **agentex-ui:** stop clipping agent badge hover scale and shadow ([#352](https://github.com/scaleapi/scale-agentex/issues/352)) ([b49fab6](https://github.com/scaleapi/scale-agentex/commit/b49fab636941bb1796500d2d50388eec142e0b3d))
* **agentex:** bump aiohttp 3.13.4 -&gt; 3.14.1 (clears 11 CVEs, agentex server image) ([#359](https://github.com/scaleapi/scale-agentex/issues/359)) ([3001351](https://github.com/scaleapi/scale-agentex/commit/3001351244307ff5d3cb01d1d1bfbb2ebdc2b035))
* **agentex:** bump ddtrace to &gt;=4.8.2 (CVE-2026-50271) ([#364](https://github.com/scaleapi/scale-agentex/issues/364)) ([2913fe0](https://github.com/scaleapi/scale-agentex/commit/2913fe095c55f50f520b3471c6900d5bea642a20))
* **authz:** grant legacy agent register principal ([#325](https://github.com/scaleapi/scale-agentex/issues/325)) ([cae5f94](https://github.com/scaleapi/scale-agentex/commit/cae5f9470c03a0c14371981a78540c4d7052819d))
* **deps:** cap fastapi &lt;0.137.0 to stop OPTIONS preflight 500s ([#334](https://github.com/scaleapi/scale-agentex/issues/334)) ([acbe9e3](https://github.com/scaleapi/scale-agentex/commit/acbe9e3957ad3867a9793d1726e07141da691f47))
* **deps:** clear golden-image Trivy CRITICAL/HIGH (litellm, starlette, pyjwt, python-multipart) ([#320](https://github.com/scaleapi/scale-agentex/issues/320)) ([bfa6652](https://github.com/scaleapi/scale-agentex/commit/bfa6652b8125dcd6beee471f21ffa313c107551b))
* page ready agents during health-check startup ([#345](https://github.com/scaleapi/scale-agentex/issues/345)) ([2ffde24](https://github.com/scaleapi/scale-agentex/commit/2ffde244f2c9ecb2b2318eaf34ce36aa9e31005d))
* **schedules:** backfill agent_run_schedules deleted_at/version on early-deployed envs ([#341](https://github.com/scaleapi/scale-agentex/issues/341)) ([fc1ba55](https://github.com/scaleapi/scale-agentex/commit/fc1ba556ff12a1fc0df8aace544f690bed97b3c7))
* **schedules:** grant legacy auth for run schedules ([#344](https://github.com/scaleapi/scale-agentex/issues/344)) ([648e81c](https://github.com/scaleapi/scale-agentex/commit/648e81cf6d9513a309a9475c228eea3ab0bf7353))
* **schedules:** include timezone data in backend image ([#370](https://github.com/scaleapi/scale-agentex/issues/370)) ([2c4f061](https://github.com/scaleapi/scale-agentex/commit/2c4f061569a4249d47b27233f01c3aa9054341fe))
* **schedules:** load live fields in schedule lists ([#368](https://github.com/scaleapi/scale-agentex/issues/368)) ([c045ad0](https://github.com/scaleapi/scale-agentex/commit/c045ad023ac3be1df79032494d851f43d6c26c3a))
* **schedules:** use stable handles for run schedules ([#349](https://github.com/scaleapi/scale-agentex/issues/349)) ([3b722f6](https://github.com/scaleapi/scale-agentex/commit/3b722f66a30092f936de638ab861d2e06c202542))
* **streams:** cut SSE error-log volume and add Redis pool headroom ([#340](https://github.com/scaleapi/scale-agentex/issues/340)) ([352eaaa](https://github.com/scaleapi/scale-agentex/commit/352eaaae082ca08a576b20880333493e449da1be))
* **streams:** snapshot SSE cursor before "connected" to stop first-token drops ([#330](https://github.com/scaleapi/scale-agentex/issues/330)) ([7c2ccfd](https://github.com/scaleapi/scale-agentex/commit/7c2ccfd61376ddeaa2ae5580bae7421adea5ffd6))
* **tasks:** preserve task_metadata in combined update and forward merge_params by name ([#336](https://github.com/scaleapi/scale-agentex/issues/336)) ([8c25c64](https://github.com/scaleapi/scale-agentex/commit/8c25c6417b6d39e2fa4457cad6ff4c37f2c952db))
* **ui:** load all agents so the picker and deep-links work past the first page ([#347](https://github.com/scaleapi/scale-agentex/issues/347)) ([92b9da3](https://github.com/scaleapi/scale-agentex/commit/92b9da3c81d0e5f04d5ca2f748db694f765b376e))


### Documentation

* document Redis as a required dependency ([#343](https://github.com/scaleapi/scale-agentex/issues/343)) ([4c1740b](https://github.com/scaleapi/scale-agentex/commit/4c1740bf576eacdf2f3f4251cf1c93803b16368f))
* **guides:** tracing, framework-agent, and local-sandbox guides ([#339](https://github.com/scaleapi/scale-agentex/issues/339)) ([b43e8c3](https://github.com/scaleapi/scale-agentex/commit/b43e8c3f0d6a586e1ae676793245cc004e558c48))
* **streaming:** document the unified harness surface ([#337](https://github.com/scaleapi/scale-agentex/issues/337)) ([31fd697](https://github.com/scaleapi/scale-agentex/commit/31fd6975624d4842ca9314ee6cbd17717a0e16a5))
