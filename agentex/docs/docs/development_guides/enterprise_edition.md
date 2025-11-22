# Enterprise Edition

## Overview

Agentex Enterprise Edition offers enhanced capabilities to support, monitor, and evaluate Agentex agents. The video below gives a brief demo of the what the developer experience would look like with Agentex's enterprise features enabled 


<video controls width="100%" >
  <source src="https://github.com/user-attachments/assets/cccb6211-281c-49d5-b24c-6730ae576b14" type="video/mp4">
</video>

## Why Open Source?

At Scale, we've spent the last three years building enterprise AI agents and learned how different every use case is. To unify our approach, we built a single delivery framework and now we're open-sourcing it to share what we've learned. Many enterprises have built upon open source tooling, and we want to contribute to that ecosystem. Our goal is simple: see more useful AI in production.

Agentex is also cloud-agnostic and Kubernetes-native. We intentionally kept it lightweight and unopinionated to maximize flexibility and to incur minimal infrastructure and security overhead.

Here are the differences between Open Source vs Enterprise to meet different organizational needs:

| Feature | Open Source Edition | Enterprise Edition |
|---------|--------------------|--------------------|
| **Source Code** | ✅ Open source server, developer UI, and SDK | ✅ Open source server, developer UI, and SDK |
| **Local Development** | ✅ Use this repo for local development | ✅ Use this repo for local development |
| **Community Support** | ✅ GitHub issues, discussions, pull requests | ✅ GitHub issues, discussions, pull requests |
| **GitOps Setup** | ❌ DIY deployment using public helm charts and the `agentex` CLI in CI/CD | ✅ Scale sets up CI/CD on select repositories for automatic agent deployment |
| **Builder Tools** | ❌ Bring your own (vector stores, models, etc.) | ✅ Model inference, knowledge bases, etc. |
| **Agent Operations (AgentOps)** | ❌ Not included | ✅ Full agent lifecycle management: hosting, version control, interaction UI, tracing, evaluation |
| **Identity Management** | ❌ No user management | ✅ SSO/SAML authentication, centralized API key management |
| **Enterprise Operations** | ❌ Self-service setup | ✅ Uptime/availability SLAs, security reviews, deployment, installation, ongoing maintenance |

**Ready for Enterprise?** Contact our team at https://scale.com/demo to discuss your requirements.

> For our current and future customers, Agentex is a module that is hosted and deployed as part of the Scale GenAI Platform's Enterprise License. This open source project is meant to give people a local development ability and community support.