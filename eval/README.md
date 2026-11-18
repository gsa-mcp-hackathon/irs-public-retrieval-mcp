# Evaluation methods and observed outcomes

Reusable [agent-through-MCP evaluation](phoenix/README.md) now supplies caller-selected public cases, actual tool-return recording, independent source checks, optional Phoenix traces, and model verdicts. Execution receipts retain their own attained scope alongside earlier recorded workflows below.

Recorded workflows reached requested IRM passages, selected official catalog products, and acquired PDFs through all three MCP tools. Independent comparisons also exposed misleading navigation, overlapping catalog editions, and generated answers that lost source conditions despite successful retrieval. These results support useful research assistance while identifying further tests.

Selected [4:40 captioned workflow](../docs/irs-public-mcp-recorded-workflow.mp4) demonstrates recorded requests/results. [Supplemental presentation](../docs/hackathon-presentation.pptx) places embedded playback immediately after cover, followed by methods, observed outcomes, and technical detail. Neither artifact requires live judge access to development environments.

## November 16 live-agent outcomes

Actual three-case suite reached two IRM answers and selected Form 1040/2024 with five complete PDF deliveries. Source review found useful date-rule application alongside literal substitutions, incorrect nested URL attachment, invented citations, and unsupported operational claims. PDF-case answer generation ended with upstream HTTP 413 and empty answer after successful artifact retrieval. Client exit 0 records completed experiment and cleanup; answer quality keeps case-specific findings.

| Public question | Attained result | Source-checked answer findings |
| --- | --- | --- |
| Reproduce native IRM date fields verbatim, with roles and body/navigation relationships | One actual IRM return; answer retains five date meanings and distinct effective/subsection roles sharing date text. | All five requested character-exact values change ASCII hyphens or spaces. Calendar meanings remain recognizable. Answer also assigns nested body to `#id46`, despite correctly reporting that target reaches unrelated `1.11.2.3.3`; matched parent body is `#id77`. |
| Apply filing-season rules to publication December 15, 2026 and effectiveness January 1, 2027 | One actual IRM return; MT, effective, affected specified subsection, PDF revision, and index revision values follow hypothetical inputs and returned rules. | Fabricated line citations lack returned coordinates. Two-week processing sufficiency, publication after MT, claimed XML authoring sequence, and automatic revision population lack source support. Actual processing sufficiency remains unresolved. |
| Select annual catalog Revision Date 2024, then retrieve linked Form 1040 PDF | Correct prior-catalog row found. Five successful document calls each deliver complete 163,287-byte PDF, HTTP 200, official URL, and `application/pdf`. | Upstream request-size rejection (HTTP 413) ends generation with empty answer. Artifact integrity is supported; printed edition and successful model PDF inspection remain unassessed. |

PydanticAI selected actual tools through stdio MCP. Expected answers stayed outside generation inputs; evaluators received retained references and tool evidence. Independent checks compared literal characters with role-qualified source fields, decoded complete returned PDFs, checked byte counts/signatures/MIME/URIs, and reviewed source claims. Questions, portable receipts, and case findings appear under `agent_through_mcp_runs` in [observations](observations.json). Original `observations` array remains **13 selected records**; new **three-case suite** has separate scope, without answer-pass denominator or statistical ranking.

Agent and model judges used identical configured model alias and endpoint; backend revision remains unattested. Correctness labels say `correct` for every case, with null numeric scores. Source checks contradict their full-success implications: first answer changes requested literals and nested URL, second adds unsupported claims, and PDF case supplies no generated answer. Scope judgments also disagree or add unsupported interpretations, including rejection of legitimate caller-supplied scenario years and misdescription of complete PDF bytes as excerpt. Judge labels therefore remain model outputs beside source-checked findings.

Installed client conversion omitted URI and structured acquisition metadata from model-facing PDF BinaryContent, while raw MCP returns retained both. Repeated identical artifacts reached client before upstream 413; retained evidence establishes no universal request threshold, PDF-modality failure, or cause of repeated retrieval. Largest successful PDF-stage prompt reports 5,276 tokens. Reported prompt sums count repeated context; failed-request input extent and judge usage remain unmeasured.

Execution ran November 16 MST / November 17 UTC, from 01:04:12.649339 through 01:16:44.368653 UTC; owned cleanup receipt completed at 01:16:48.4359988 UTC. Agent spans were approximately 12.42 seconds, 19.31 seconds, and 26.48 seconds. These intervals exclude judge work and differ from full experiment duration. Later offline compatibility or evaluator repairs supply no rerun, changed-answer, reduced-repetition, or model-inspection result for this recorded suite.

## Methods, inputs, and expected behavior

| Exercised method and inputs | Expected behavior | Observed outcome and scope |
| --- | --- | --- |
| Controlled HTML/PDF/HTTP fixtures, FastMCP serialization, and ASGI protocol cases | Preserve citation/body identity, dates, catalog context, continuation, validated origins/media, and structured failures. | Functional/protocol assertions cover these contracts. Recorded verification results below retain their own scope; fixtures supply no representative live-site or model-accuracy denominator. |
| Native agent task: explain IRM `1.11.2.5.2`; find and acquire Form 1040 associated with revision `2024` | Agent selects suitable tools; returned sources support requested explanation and document choice. | All three tool calls completed. Useful answers coexisted with contradictory/omitted navigation relationships and unsupported whole-section date outcome. One selected task took approximately **50.68 seconds end to end**, including client, tools, model work, and overhead; isolated server latency remains unmeasured. |
| November 12 explicit stdio workflow: same IRM citation, prior-catalog `1040`/revision `2024`, then selected PDF URL | Requested body resolves; catalog exposes matching product and further pages; document acquisition follows actual selected result. | IRM matched **Determine IRM Dates** at `#id77`. Catalog returned 25 matches from **Showing 1–25 of 73**, with Next. Selected official PDF returned HTTP 200, `application/pdf`, and **163,287 bytes**. Explicit caller selection supplies integration evidence, distinct from autonomous agent selection. |
| Independent source-to-answer comparisons and source-cued reconsiderations | Preserve supported navigation, conditions, date meanings, and literal claims through explanation. | Comparisons found useful coverage plus hierarchy, applicability, omission, and exact-form errors. Selected reconsiderations repaired some claims. Changed context/routes prevent controlled-improvement claims; separate public-only answer had zero tool access. |
| Current/prior catalog continuation and retained PDF page reading | Preserve product/revision context, expose incomplete coverage, and verify printed identity through inspection. | Initial request plus one continuation per catalog reached 50 query rows per catalog with Next remaining. Selected current/prior 2025 PDF responses matched at **220,237 bytes** each; complete two-page text reading identified printed Form 1040/2025. Independent reading supplies no native model PDF-understanding claim. |
| Installed package, dependency/import, HTTP health, initialization, and discovery checks | Packaged server exposes supported interface through maintained local routes. | Recorded checks exposed complete three-tool interface. Discovery establishes neither IRS retrieval nor target judge-environment execution. |

Native agent task occurred October 26 MDT / October 27 UTC. Later explicit stdio workflow occurred November 12, approximately 17:42–17:47 MST. [Editable presentation source](../docs/hackathon-presentation.json) retains portable later-workflow summary under source `stdio-nov12`; fuller local receipts remain separately retained. [Portable observations](observations.json) still contain **13 selected records**, combining supplementary/repeated views rather than 13 independent benchmark cases. Later local checks supplement that dataset without silently changing its count.

Recorded task intervals, tool-call counts, PDF bytes/page counts, and reported token usage support particular runs. Broad latency distributions, representative accuracy, controlled no-tool benefit, cost savings, and further outcomes require their own measurements.

## Source-checked answer: IRM date selection

Retained IRS response acquired November 4 MST / November 5 UTC includes IRM 1.11.2.5.2 and nested IRM 1.11.2.5.2.1. November 16 owning source comparison adopts guidance below from complete retained [tool response](runs/2026-11-04/actual-mcp-irm/source-result.json). Source scope remains attached; no fresh IRS lookup occurred. [Official source](https://www.irs.gov/irm/part1/irm_01-011-002#id77).

### Select dates by role and applicable conditions

| Date role | Selection and format |
| --- | --- |
| Manual Transmittal date | M&P publication/posting date in Core Repository of Published Products. Source format: `Month DD, YYYY`; M&P inserts MT date into IRM XML. |
| IRM effective date | Date revised/new section becomes effective; same as MT date or specified future date. Filing-season IRMs require specific effective dates. Source shows wildcard `(MM-DD-YYYY)` and specific-date example `(01-01-2026)`. Effective-date wildcard becomes MT date during publication. |
| Subsection date | Effective date for subsection information. Source lists revision date or effective date as possible dates, then supplies detailed cases below. Formats include wildcard `(MM-DD-YYYY)` or specific date. Subsection-date wildcard becomes IRM effective date during publication. |
| Revision date | Reflects MT date; appears in PDF IRMs and Document 10988, IRM Index. Formats: `(MM-DD-YYYY)` for PDF, `MM-YYYY` for index. |

For specified effective dates, choose dates equal to or later than MT date and allow sufficient M&P processing time. Source especially emphasizes August–December publishing period. Use specified subsection dates, avoiding wildcard subsection dates. Insert specified dates into MT effective-date element and affected subsection-date elements. Example publication `December 15, 2025` with effectiveness `01-01-2026` illustrates differing MT/effective dates; example revision values `12-15-2025` and `12-2025` retain illustrative scope. [Date rules](https://www.irs.gov/irm/part1/irm_01-011-002#id77).

Substantive changes concern procedural or operational matters. Apply all supplied subsection cases:

| Subsection situation | Resulting subsection date |
| --- | --- |
| Substantive changes | IRM effective date. |
| Editorial changes here; substantive changes elsewhere in section | Existing subsection date. |
| Editorial changes only throughout section | Date instructed by IRM 1.11.2.8.1, Editorial Update Process; detailed referenced instructions fall outside supplied passage. |
| Issued IPU incorporated without subsequent substantive changes | IPU issue date. |
| Issued IPU incorporated with subsequent substantive changes | IRM effective date. |
| IGM content incorporated without subsequent substantive changes | IGM effective date. |
| IGM content incorporated with subsequent substantive changes | IRM effective date. |

[Subsection rules within returned parent passage](https://www.irs.gov/irm/part1/irm_01-011-002#id77).

### Keep body nesting separate from mismatched navigation

Matched body IRM 1.11.2.5.2 includes nested IRM 1.11.2.5.2.1. Supplied TOC entries instead have mismatched labels and destinations:

| TOC label | Supplied target | Reached body |
| --- | --- | --- |
| `1.11.2.5.2 Determine IRM Dates` | [id44](https://www.irs.gov/irm/part1/irm_01-011-002#id44) | `1.11.2.3.2`, `IRM Catalog Number` |
| `1.11.2.5.2.1 Determine the Subsection Date` | [id46](https://www.irs.gov/irm/part1/irm_01-011-002#id46) | `1.11.2.3.3`, `Identify the IRM Owner` |

These mismatches establish TOC-label/target disagreement. Matched body citations govern requested passage identity; supplied relationships support no higher-level catalog hierarchy between requested subsection and these targets.

### Preserve returned date fields verbatim

| Exact source value | Source meaning/context |
| --- | --- |
| `10-Jun-2026` | Page Last Reviewed or Updated |
| `June 09, 2026` | Manual Transmittal date |
| `06-09-2026` | IRM effective date |
| `06-09-2026` | Subsection date for IRM 1.11.2.5.2 |
| `09-13-2023` | Subsection date for IRM 1.11.2.5.2.1 |

Date spellings retain ASCII hyphens and ordinary ASCII spaces from supplied fields. [Public document](https://www.irs.gov/irm/part1/irm_01-011-002).

### Form 1040/2024 limits in retained November 4 IRM-only packet

Retained IRM-only response acquired November 4, 2026, at 17:22 MST (`2026-11-05T00:22:18.575187+00:00`) underlies earlier public-only answer and November 16 authored reference above. That supplied packet contains no Form 1040/2024 catalog row, acquired PDF, or PDF-inspection result; its limitation concerns this IRM-only input. November 16 actual agent suite separately selected Form 1040/2024 and received five complete PDFs. Printed edition and successful model inspection retain that suite's own unassessed findings.

### Drafting, review, and adopted guidance

November 16 contributing-model work supplied useful material alongside errors. Owning source checks determined adopted reference above.

| Contribution | Observed effects and source checks |
| --- | --- |
| Configured GPT-OSS draft | Restored mandatory filing-season requirement, procedural/operational definition, all seven subsection cases, and correct TOC/body distinction. Five rows claimed verbatim changed source characters; practical steps also narrowed specific-date rules incorrectly. Source comparison repaired those relationships. |
| Distinct configured Llama audit | Issued missing-content findings for already-present draft material and incorrectly approved character-exact dates. Rewritten ASCII dates were useful, while specific-date narrowing persisted and later ordering comparator disappeared. Useful rewritten content and review verdict retain separate findings. |

Both generic public-source client invocations completed with natural stop and exit 0. Recorded client intervals were 30.5694512 seconds for drafting and 75.2133574 seconds for audit, including client work; isolated model-compute latency and cost remain unmeasured. Configured routes identify intended model selections, without independent backend-weights/revision attestation. Both received selected public source and newly authored instructions/criteria; audit additionally received ordinary draft. Neither invocation used MCP tools. Source bytes remained unchanged.

Reference is authored source-checked guidance, distinct from raw generated answers and autonomous agent verification. New prompts, criteria, contexts, and configured routes differ from earlier observations, so useful repairs supply no controlled-improvement or model-ranking result. Existing 13 portable observation records retain their original contents and counts; this later comparison supplements current guide without reclassifying historical runs.

## Selected source comparisons

Public-only Certara [answer](runs/2026-11-04/certara-public-irm/answer.txt) preserves seven descendant decision-table cases and correctly localizes unavailable Form1040 catalog/acquisition findings to supplied input. Correct navigation table coexists with later unsupported hierarchical links, omitted filing-season/substantive-change conditions, quotation paraphrases, and changed characters in claimed exact dates. [Assessment](runs/2026-11-04/certara-public-irm/assessment.md) retains useful coverage, gaps, and question-wording hypothesis with unmeasured causal contribution. [Run](runs/2026-11-04/certara-public-irm/run.json) and complete public [request](runs/2026-11-04/certara-public-irm/request.json) bind original composite question to supplied public IRM data and generic direct Chat Completions, without native Codex context or model tool access. Changed route/context supplies no controlled-improvement, autonomous tool-use, internal-code-review completion, or aggregate pass claim.

Actual local MCP follow-through returned matched IRM `1.11.2.5.2` body, both TOC/body mismatch records, five attributed dates, and conditional date rules needed by existing assessment. [Complete response](runs/2026-11-04/actual-mcp-irm/source-result.json), [run](runs/2026-11-04/actual-mcp-irm/run.json), and [qualitative assessment](runs/2026-11-04/actual-mcp-irm/assessment.json) preserve one successful call, fresh source clocks, and interpreted qualifications. November 3 [source-cued model run](runs/2026-11-03/source-cued-irm/run.json) used zero MCP calls; its [answer findings](runs/2026-11-03/source-cued-irm/assessment.json) remain unchanged. November 4 retrieval supplied source data; November 16 authored reference uses retained data while historical model findings keep their original run scopes.

Selected catalog follow-through found current Form 1040 revision 2025 and prior revision 2024, followed one observed continuation hop per catalog, and retained Next after 50 query rows per catalog. Selected current/prior 2025 PDF responses matched byte-for-byte at recorded retrieval clocks: 220,237 bytes each. Independent complete two-page extracted-text reading confirmed printed Form 1040/2025 identity; font-encoding warnings and rendering/model-understanding limits remain explicit.

[Evaluation records](observations.json) contain 13 observations: original eight through October 28, two October 30 catalog/document records, November 3 source-cued answer comparison, and November 4 local / November 5 UTC actual IRM tool follow-through plus public-only Certara answer. Original compilation and proposal scope remain dated October 28; added records retain independent execution, acquisition, extraction, and reading clocks where evidenced. [README overview](../README.md#evaluation-observations) summarizes results and limits. Public records preserve portable source URLs, caller inputs, observed fields, hashes, and qualifications; fuller local execution receipts remain separately retained.

## Recorded methods and results

Live retrieval supplied requested IRM date passages, official Form 1040 catalog identity, and 163,287 source-bound PDF bytes. Independent extraction and complete reading of both retained PDF page texts confirmed printed Form 1040 product/year identity for 2024. PDF acquisition, independent local reading, and model PDF understanding retain separate evidence.

Native tool use supplied useful results for both requested IRS subjects. Source comparisons found omitted navigation relationships, compressed conditional date rules, and unsupported certainty. Source-cued reconsiderations repaired selected claims while remaining omissions, changed date attribution, and literal-form problems retained independent findings. Fresh actual IRM dispatch returned six block texts, matched identity, navigation, and dates equal to November 3 retained source, with empty `links` arrays additionally exposed. Interpretation preserves specific-effective-date applicability, M&P processing time, filing-season context, editorial-only scope, and separate date meanings. Direct-tool follow-through generated no model answer; separate public-only model observation retains its own context and effects. Per-observation `observed` and `limits` fields retain exact effects and qualifications.

Recorded measurements include per-run clocks, tool-call counts, PDF byte/page/text counts, and native reported token usage. Coverage remains selected local executions and source comparisons, without representative benchmark or aggregate accuracy claims.

## Supporting verification

`supporting_verification` records earlier implementation/protocol checks at commit `7627994667c98966d907512161cc4b7c91b8ca1c`: 120 tests plus 41 subtests passed, alongside Ruff lint and formatting. Later combined feature/interface verification returned **147 passed, 41 subtests, and three offline IBM-registration 60-second timeouts**, taking 527.87 seconds. Those registration cases selected synthetic/local targets rather than IBM service endpoints. Failures retain registration scope rather than establishing failed IRS retrieval.

Diagnostic-only addition at `8dc0befd5136feb3160f891c859122df40d0d473` passed selected diagnostic check 1/1. Two later replays passed original assertions in 50.737 and 47.804 seconds. These later successes retain separate scope; complete combined suite was not rerun after diagnostic-only change. [Presentation source register](../docs/hackathon-presentation.json) retains supporting verification summaries without replacing earlier observation records.

Separate noneditable installed-package validation for candidate landed as commit `5f3aa3ec88f080891fcf9c337d44a1c3221ccdfe` passed dependency compatibility, isolated imports, HTTP health, MCP initialization, and complete three-tool discovery.

Regression and package checks retain their recorded execution scope. Representative agent answer accuracy, Linux Python 3.11 container builds, and hosted-platform acceptance require separate evidence.

## Security considerations and lessons

`security_considerations` covers anonymous public reads, supported-origin/redirect validation, deployment TLS/proxy settings, optional request budgets, and untrusted retrieved text. Administrative hosting authentication and model-provider credentials retain separate purposes. Selected source-faithfulness comparisons establish no adversarial or prompt-injection resistance.

`lessons` distinguishes successful dispatch, useful retrieval, faithful explanation, and PDF understanding. Source identity, conditional rules, literal forms, catalog continuation, and acquisition-versus-publication clocks need preservation through answer composition. Partial answer repair and package verification retain their documented limits.

## Follow-through and open evaluation work

Five `proposed_next_cases` preserve original IRM date/navigation, catalog edition/continuation, document receipt/inspection, retrieval-failure/untrusted-text, and controlled-comparison questions. October 30 catalog/document observations and November IRM observations exercise selected existing-case relationships; remaining catalogs, additional documents, repeats, controlled baselines, scored measurements, and broader cases retain open scope. Original `proposal_scope` describes October 28 documentation, while `follow_through_scope` records later bounded execution. Dataset size, evaluator, model, acceptance criteria, and measurement procedure remain caller selections; case coverage remains expandable.

`unmeasured` retains representative aggregate accuracy, broad latency distribution, controlled tool-versus-no-tool benefit, adversarial robustness, native model PDF understanding, and hosted-platform acceptance. Existing observations retain credit independently from those open measurements.
