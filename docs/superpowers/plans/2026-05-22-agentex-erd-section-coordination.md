# AgentEx ERD Subsection Landing — Coordination Plan

> **Note on format:** This is a coordination plan, not a software-implementation plan. Steps are discrete operator actions rather than TDD cycles. The subagent-driven-development and executing-plans skills do not apply; the operator runs this themselves.

**Goal:** Land the AgentEx per-service catalog bullets in the parent ERD (`ERD: SGP Service Decomposition and Catalog`), replacing the current "Stub — to be populated by the AgentEx team" placeholder.

**Approach:** Run an internal AgentEx team review of the full spec, get explicit sign-off from the `sgp-agent-deploy` owner on the boundary section, give OneAuth folks an informational heads-up, decide where the AgentEx-internal mini-ERD lives, then paste the catalog bullets into the parent Notion page.

**Source artifact:** `docs/superpowers/specs/2026-05-22-agentex-erd-section-design.md`

---

## Scope: what lands upstream vs. what stays internal

The parent ERD is the SGP decomposition ERD. Only the per-service catalog bullets need to land there:

- `agentex-state`
- `agentex-conversations`
- `agentex-tasks`
- `agentex-control-plane`
- `agentex-auth`

The rest of the spec (Problem Statement, Solution Statement, Service Inventory, Boundaries section, Forward-looking notes) is the AgentEx-internal mini-ERD. It either stays as the `docs/superpowers/specs/` artifact only, or becomes a separate Notion page linked from the parent ERD. Decision is Task 4 below.

---

## Task 1: AgentEx team internal review

**Goal:** AgentEx team consensus that the spec reflects our direction.

- [ ] **Step 1:** Share the spec with the AgentEx team
  - Post in the AgentEx team's primary review channel with: link to `docs/superpowers/specs/2026-05-22-agentex-erd-section-design.md` (or the branch `agentex-erd-section-design` on GitHub once pushed), one-paragraph summary, deadline for feedback (suggested: one week).
- [ ] **Step 2:** Collect feedback
  - Address blocking feedback by editing the spec on the branch and committing.
  - Items framed as "we should think about this later" go into the spec's Forward-looking notes section rather than the catalog bullets.
- [ ] **Step 3:** Verify consensus
  - Each blocking comment has been resolved (responded to in-thread or by a spec edit).
  - No outstanding "we disagree with this whole direction" feedback.
- [ ] **Step 4:** Commit any spec updates from review
  - Use a single commit per round of feedback, message format: `docs(spec): incorporate AgentEx team review feedback - <one line>`

---

## Task 2: Cross-team alignment — `sgp-agent-deploy` boundary

**Goal:** Written acknowledgment from the `sgp-agent-deploy` owner that the boundary section matches their understanding.

- [ ] **Step 1:** Identify the `sgp-agent-deploy` owner
  - From the parent ERD page properties, or by asking the parent ERD author. (The parent doc lists the service in the inventory; the owner is the natural review contact.)
- [ ] **Step 2:** Share the Boundaries section
  - Send the "Boundaries with adjacent services → `agentex-control-plane` ↔ `sgp-agent-deploy`" section text directly (not just a link — they may not want to read the full spec).
  - Ask explicitly: "Does the handoff as described — `sgp-agent-deploy` ends at pod running, `agentex-control-plane` begins at agent self-registration, no direct API call between the two — match your understanding?"
- [ ] **Step 3:** Capture the response
  - If acknowledged: capture the confirmation (Slack permalink or Notion comment).
  - If disputed: revise the Boundaries section accordingly, commit, and re-confirm.
- [ ] **Step 4:** Verify
  - Boundaries section has explicit sign-off from the `sgp-agent-deploy` owner.

---

## Task 3: Cross-team alignment — OneAuth direction (informational)

**Goal:** OneAuth folks are aware that AgentEx has the `agentex-auth` → `sgp-identity` fold-in as a forward-looking item; not a gate.

- [ ] **Step 1:** Identify the OneAuth lead
  - The parent ERD or `sgp-identity` documentation should name this person.
- [ ] **Step 2:** Send a brief informational note
  - Share the relevant Forward-looking notes bullet from the spec.
  - Frame it as a heads-up: "AgentEx is keeping `agentex-auth` standalone in the near term; if OneAuth ends up consolidating, we'll need to revisit. No action needed from your side right now."
- [ ] **Step 3:** Capture any pushback
  - If the OneAuth lead has strong feelings about timing or commits AgentEx to a specific direction, capture in the spec's Forward-looking notes or as a Boundaries section addendum.

---

## Task 4: Decide where the AgentEx-internal mini-ERD lives

**Goal:** Pick one of two locations for the Problem Statement / Solution Statement / Service Inventory / Boundaries / Forward-looking notes content.

- [ ] **Step 1:** Pick one of:
  - **Option A — stays in repo only.** Internal mini-ERD lives as `docs/superpowers/specs/2026-05-22-agentex-erd-section-design.md`. No Notion presence beyond the catalog bullets in the parent ERD. Cheapest. Loses visibility for non-AgentEx folks who want to dig in.
  - **Option B — Notion page linked from parent ERD.** Create a Notion page titled "AgentEx Decomposition" containing the same content; link to it from the AgentEx subsection of the parent ERD. Higher visibility, more upkeep (two sources of truth — pick one as canonical).
- [ ] **Step 2:** If Option B: create the Notion page
  - Copy the relevant sections from the spec into Notion. Mark the Notion page as canonical (and add a note at the top of the repo spec pointing to it).
- [ ] **Step 3:** If Option A: skip — done.

---

## Task 5: Land the catalog bullets in the parent ERD

**Goal:** "AgentEx services" subsection of the parent ERD's All-up SGP Service Catalog contains the five catalog bullets, replacing the current "Stub" placeholder.

- [ ] **Step 1:** Confirm Tasks 1, 2, 3, 4 are complete
  - Internal review consensus ✓
  - `sgp-agent-deploy` boundary acknowledged ✓
  - OneAuth heads-up sent ✓
  - Mini-ERD location decided (and Notion page created if Option B) ✓
- [ ] **Step 2:** Get write access to the parent ERD page
  - Either edit access directly, or coordinate with the parent ERD owner to paste on your behalf.
- [ ] **Step 3:** Paste the five catalog bullets
  - Copy verbatim from `docs/superpowers/specs/2026-05-22-agentex-erd-section-design.md`, "Per-service catalog bullets" section.
  - Replace the current "Stub — to be populated by the AgentEx team. AgentEx platform code lives in `scale-agentex/` (`agentex`, `agentex-ui`) and agent implementations live in `agentex-agents/teams/*`." line.
- [ ] **Step 4:** If Task 4 chose Option B: add a "See also" link
  - Below the catalog bullets, add: "See [AgentEx Decomposition](link) for the AgentEx-internal mini-ERD."
- [ ] **Step 5:** Verify
  - Catalog bullets render correctly in Notion.
  - Service names link consistently with how other catalog bullets handle service references (e.g. backticks or Notion mentions).

---

## Task 6: Announce

**Goal:** Notify AgentEx team and parent ERD audience that the section has landed.

- [ ] **Step 1:** Post in the AgentEx team's primary channel
  - One-paragraph note: "AgentEx subsection of the parent ERD is now populated. Link: [parent ERD section]. Internal mini-ERD: [Notion page or repo path]. Open to follow-up questions."
- [ ] **Step 2:** Notify the parent ERD owner
  - "AgentEx section is in. Stub line replaced with five catalog bullets. `sgp-agent-deploy` boundary signed off by [owner]. OneAuth heads-up sent. No outstanding open questions."
- [ ] **Step 3:** Update the spec's status
  - Edit `docs/superpowers/specs/2026-05-22-agentex-erd-section-design.md` header: change `Status: Draft, in review` to `Status: Landed in parent ERD on YYYY-MM-DD`.
  - Commit: `docs(spec): mark agentex ERD section as landed`

---

## Definition of done

- AgentEx subsection in parent ERD contains the five catalog bullets (no longer "Stub").
- `sgp-agent-deploy` owner has explicitly acknowledged the Boundaries section.
- OneAuth folks have been informed of the forward-looking item.
- Mini-ERD location decided (Option A or B).
- AgentEx team and parent ERD owner notified.
- Spec status updated.

---

## Out of scope (and why)

These are deliberately not in this plan:

- **Building the Go services.** Each extraction is its own multi-week initiative that needs its own design pass before it can be planned. This plan only lands the design document.
- **Mongo→Postgres performance load tests.** These happen at the start of extraction 1, not during this coordination work.
- **Per-extraction sequencing details (dress rehearsal protocol, cutover specifics).** Each extraction will have its own design and plan.
- **Retiring the `spans` endpoints.** Already in progress separately; spec only notes the direction.
