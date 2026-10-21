# Interviewing and evidence examples

Use this reference when raw material is incomplete or a bullet needs a better balance of mechanism and impact. Examples are fictional teaching material. Their facts and numbers belong only to the stated examples.

## Choose a question that changes the draft

| Material already supplied | Useful follow-up | Decision the answer enables |
| --- | --- | --- |
| "Added Redis caching; the API became faster." | "Which endpoint changed, and do you have comparable before/after latency or database-load observations? Was this measured in production or a test?" | A scoped performance result, or a capability statement without an invented improvement. |
| "Our team migrated the billing system." | "Which part did you own, and what rollout or acceptance result can you describe?" | Accurate personal contribution and delivery scope. |
| "Automated weekly reporting in Python." | "What manual steps did it replace, who used the output, and is preparation time known?" | A concrete workflow result, with time savings only when supported. |
| "Improved model accuracy by 15%." | "What metric, baseline, resulting value, and evaluation set does that refer to?" | Correct metric wording and percentage versus percentage-point interpretation. |
| "Built a Kubernetes deployment tool" for a platform role | "What made deployments difficult, and what capability did your tool add?" | A distinguishing mechanism instead of another technology list. |
| A source file implements retries | "Was this used beyond the prototype, and which part was your work?" | The boundary between implemented code, deployment, and personal ownership. |

These are question candidates, not a checklist to send wholesale. Ask for the missing fact, rather than asking the user to approve a guessed result. If only one number is ambiguous, keep the question on that number.

## Match evidence to the claim

Prefer a directly observed result with relevant context. A defensible estimate can also be useful when its inputs and limitations are clear. When no impact measure exists, use confirmed scope or a concrete deliverable. When even the outcome is unknown, describe the implemented mechanism and ask about its use; do not imply adoption or success.

| Claim type | Context that may matter | Common distortion to prevent |
| --- | --- | --- |
| Throughput | Requests or jobs per unit time; workload and resources | Comparing unlike workloads or equating throughput with concurrency. |
| Latency | Endpoint, percentile, unit, load, comparison | Replacing p95 with average latency or treating a microbenchmark as production. |
| Accuracy or quality | Metric, evaluation population, baseline, resulting value | Calling every score "accuracy" or hiding a changed evaluation set. |
| Cost | Currency, period, workload, included resources | Claiming unit-cost savings when only total workload fell. |
| Coverage | What is covered and its denominator | Presenting code coverage as evidence of fewer production defects. |
| Reliability | Incident definition, observation window, scope | Inferring an availability guarantee from a short incident-free period. |
| Time saved | Previous and resulting effort, frequency, number of people | Turning elapsed runtime into human labor savings. |
| Adoption or scale | Active versus registered users; team or customer scope | Counting a potential audience as actual usage. |

An increase from 80% to 92% is **12 percentage points**, or a **15% relative increase**. A reduction from 400 ms to 250 ms is a **37.5% latency reduction**. Report the clearest representation for the reader; a percentage is not automatically better than before/after values.

Keep detailed measurement notes in working context. The resume needs the context that changes interpretation, not an experimental methods section. Use an anonymized description or a user-supported range when exact internal information cannot be shared; never request confidential raw logs merely to strengthen a bullet.

## Worked examples

### 1. A useful metric arrives after a focused question

Initial material: "I built report-export workers with Python and batched SQL reads. Exports used to be slow."

Supported first draft:

> Built Python workers with batched SQL reads for report export.

Follow-up: "Do you have comparable export timings, dataset size, and the measurement setting?"

User adds: "On the same 100,000-row dataset in staging, elapsed export time fell from 18 to 6 minutes. I owned the worker implementation."

Revised bullet:

> Cut export time from 18 to 6 minutes on a 100,000-row staging dataset by building Python workers with batched SQL reads.

This retains the test context, uses only supplied facts, and explains the mechanism. It does not claim production performance or staff time saved.

### 2. No number is available

Material: "I made a Python script that validates release configuration and comments on pull requests. We use it in the release workflow. We don't have time-saved or defect data."

> Automated release-configuration validation with a Python check that posts findings on pull requests.

The delivered workflow is specific. Do not add "reduced incidents," demand a percentage, or invent a validation rule the source did not describe.

### 3. The right technical depth

Material: "I designed and built order-event processing in Java with Kafka. Duplicate deliveries had caused repeated processing. I added PostgreSQL-backed idempotency keys and verified replay cases before rollout."

Too broad:

> Used Java, Kafka, and PostgreSQL to build a robust order system.

Too detailed:

> Added an idempotency_key column, changed the consumer handler, checked a row before each callback, and updated the transaction wrapper.

Appropriate:

> Designed idempotent order-event processing in Java with PostgreSQL-backed deduplication, validating duplicate Kafka deliveries before rollout.

The mechanism and validation distinguish the work without adding an unsupported production incident claim. Do not turn verification before rollout into proof of a completed rollout.

### 4. A shared outcome with individual ownership

Material: "Our three-person team migrated 12 services. I implemented staged rollouts and rollback checks. The team finished the migration with no customer-facing outage."

> Implemented staged rollouts and rollback checks for a three-person team's migration of 12 services, completed without a customer-facing outage.

The team result remains attributed to the team, and the individual's contribution stays concrete. Do not replace this with "Led a zero-downtime platform transformation."

### 5. An introductory project without production scale

Material: "For a course project, I built a React and FastAPI booking app with conflict detection and cancellation. Four classmates tested the main flows. It was not deployed publicly."

Overview:

> Course project: booking application built with React and FastAPI.

Bullet:

> Implemented booking-conflict detection and cancellation, testing the main booking flows with four classmates.

One strong bullet is enough here. Do not invent customers, uptime, business savings, or four more accomplishments to fill a project template.

### 6. A process accomplishment outside engineering

Material: "I coordinated customer onboarding between sales and support. I introduced a shared handoff checklist, and both teams adopted it. Completion-time data isn't available."

> Standardized customer-onboarding handoffs with a shared checklist adopted by sales and support.

The process and adoption supply evidence. Do not force software keywords or assume a conversion-rate improvement.

## Keep questions separate from usable copy

A useful response can contain a supported rewrite followed by: "To strengthen the performance claim, I still need the before/after latency and whether it came from load testing or production."

Avoid embedding "assuming this is true," "not necessarily production-grade," or a guessed percentage in the bullet. A compact factual qualifier such as "in staging" belongs in the bullet when it prevents a misleading interpretation. If the user cannot supply the missing evidence, retain the supported version and continue.
