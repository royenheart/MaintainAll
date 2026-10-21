# Resume-writing practice review

Sources reviewed on 2026-10-21. This review supports the [skill](../SKILL.md); it is maintenance context rather than a required reading list for every resume request. Open-source skills demonstrate prompt and workflow choices, not measured hiring effectiveness. The recommendations below are a synthesis of source guidance and this skill's design requirements, rather than a controlled study of interview conversion.

## Findings that change the workflow

### Evidence precedes sentence formulas

Laszlo Bock's own public post gives the familiar XYZ formulation: "Accomplished [X] as measured by [Y] by doing [Z]." Here X is the accomplishment, Y its measure, and Z the method. The linked original article was not retrievable during this review; the author's accessible restatement supports the attribution. [Bock's post](https://www.linkedin.com/posts/laszlobock_my-personal-formula-for-a-winning-resume-activity-7289686500462452736-PcrJ)

The skill uses those three concepts without forcing a fixed word order. STAR helps recover missing context and personal action; the skill then compresses that material into resume-sized evidence. Jobscan explains STAR for resume bullets and allows changes in ordering, while the decision to use it primarily during evidence gathering is this skill's synthesis. [Jobscan STAR guide](https://www.jobscan.co/blog/star-method-resume/)

Amazon's recruiters emphasize readable presentation, role-relevant accomplishments, and measured results where available. The article explicitly recognizes that some bullets do not have numerical measurements. This supports asking for useful evidence without making a metric a prerequisite for every bullet. [Amazon recruiter advice](https://www.aboutamazon.com/news/workplace/amazon-job-application-resume-writing-tips)

### Selection and concrete methods matter together

Harvard's guide emphasizes factual, specific, active language; relevance to the target position; and consistent, scannable presentation. It also cautions that country conventions vary. The skill adopts those principles while grounding actual content in the candidate's materials. [Harvard resume guide](https://careerservices.fas.harvard.edu/resources/create-a-strong-resume/)

MIT recommends selecting experience through the position description, describing how work was performed, and communicating contributions. Its guidance includes readable fonts and whitespace. A separate first-year guide explicitly allows different bullet counts for different experiences. These support technical specificity and unequal space allocation rather than a rigid template. [MIT resumes](https://capd.mit.edu/resources/resumes/), [MIT first-year guidance](https://capd.mit.edu/blog/2023/09/01/enhance-your-resume-a-guide-for-first-year-undergraduates/)

The four-to-six-bullet starting point for a substantial featured project and the one-sentence project overview are editorial defaults adapted to the user's request. These sources do not establish a universal optimum or a parsing requirement for either choice.

### ATS advice needs a defined scope

Greenhouse documents incomplete parsing caused by image-based files, columns, complex tables, and important details in headers or text boxes. Its guidance concerns extraction into candidate fields. This supports the skill's restrained layout defaults and extraction checks; it does not establish that every ATS rejects every column layout or that a given keyword score predicts an interview. [Greenhouse parsing guidance](https://support.greenhouse.io/hc/en-us/articles/200989175-Unsuccessful-resume-parse)

The skill therefore treats truthful terminology, text extraction, and human readability as separate review concerns. It follows the employer's file requirements and makes no provider-independent PDF-versus-DOCX guarantee.

## Existing skills inspected

These links pin the inspected GitHub revisions. The new skill is independently written; no upstream instruction files, scripts, templates, or personal candidate data are copied into the bundle.

| Skill and inspected source | Useful mechanism | Limitation relevant to this design | Decision here |
| --- | --- | --- | --- |
| [ComposioHQ tailored-resume-generator](https://github.com/ComposioHQ/awesome-claude-skills/blob/be2a406907dbc61b73e6827ded415c96139d13a2/tailored-resume-generator/SKILL.md) | Maps a job description to relevant experience and orders bullets by relevance. | Its worked example adds precise metrics absent from the example input despite a later truthfulness rule. It also prescribes broad page limits and routine extra recommendations. | Apply evidence discipline to examples as well as rules. Make deliverables proportional to the request. |
| [Sumukhmg resume-optimizer](https://github.com/Sumukhmg/resume-optimizer-claude-skill/blob/68917dce3bd29071728025bcc29ca37e3120677d/skill/SKILL.md), [rewrite rules](https://github.com/Sumukhmg/resume-optimizer-claude-skill/blob/68917dce3bd29071728025bcc29ca37e3120677d/resources/rewrite-rules.md) | Explicitly rejects invented metrics and ownership inflation; permits qualitative rewrites. | Requires a fixed review sequence and report, asks for existing resume text even when work history is supplied, and places confirmation markers inside suggested text. | Accept work notes directly; ask targeted questions; keep uncertainty outside usable resume copy. |
| [INIT1996 resume-builder](https://github.com/INIT1996/resume-builder/blob/c710c4d7d00b8b245cf7913c9a989a3c1bebae0d/SKILL.md) | Progressive intake, evidence-linked skills, honestly labeled practice projects, and actual print-layout inspection. | Defaults to Chinese HTML, requires template confirmation, and restricts content reduction even during general improvement. These are product choices rather than general resume requirements. | Preserve requested language and format; choose ordinary defaults without a mandatory style approval; select and consolidate content according to task scope. |

The comparison is a source review, not a popularity ranking or a behavioral benchmark of those skills. Repository stars and directory installation counts are not evidence for the quality of a candidate's resulting resume.

## Treatment of the supplied reading list

| Supplied source | Review result and use |
| --- | --- |
| [Random Recruiter XYZ article](https://randomrecruiter.substack.com/p/transform-your-resume-with-the-google-xyz-method) | Read. Gives the result/measure/method structure. Attribution is anchored to Bock's own accessible post rather than a claim about internal Google hiring policy. |
| [DesignGurus XYZ answer](https://www.designgurus.io/answers/detail/what-is-the-xyz-format-for-resume) | Read. Uses Y for method and Z for result, unlike Bock's formulation. Retain the useful action/method/result idea while naming the elements explicitly. |
| [Simplify XYZ guide](https://simplify.jobs/blog/how-to-use-the-xyz-resume-format) | Read. Discusses scope such as team size when conventional impact measures are missing. The skill distinguishes scope from improvement and does not use the article's ATS-benefit language as a proven causal result. |
| [ResumeGeni software engineer guide](https://resumegeni.com/resume-for-software-engineer) | The page remained inaccessible through the research browser after retry. No rule is presented as verified from this source. |
| [JobRise bullet guide](https://jobrise.io/en/learn/land-the-job-with-ai/resume-and-ats/rewrite-bullets-with-ai/) | Read. Explicitly permits nonnumeric results and rejects unsupported numbers. This aligns with the skill's supported qualitative fallback; unresolved questions are kept outside final copy. |
| [Jobscan STAR guide](https://www.jobscan.co/blog/star-method-resume/) | Read. Supports action and result with brief context. The skill avoids expanding every bullet into an interview-length narrative. |
| [Programmer resume article on Tencent Cloud](https://cloud.tencent.com/developer/article/1367041) | Read after retry; the page identifies a 2018 community article, not a Tencent hiring policy. Relevant points include truthful skills, personal contributions, restrained wording, and reverse chronology. Its long proficiency lists and closing courtesy sentence are not adopted. |

## Design boundaries

The targeted follow-up loop, the stop point at mechanism-level detail, separate questions outside application copy, and the balance between global selection and bullet quality are design decisions tailored to this request. The skill keeps necessary factual qualifiers, such as a staging benchmark or team contribution, while removing hypothetical defenses. Neither a formula nor a clean layout compensates for absent evidence.

The full-review coverage pass and measurement-preservation rules also reflect practical editing feedback: an overall rewrite can miss the distinctive work inside individual projects, and excessive caution about an ambiguous benchmark can erase unrelated supplied results. The resulting procedure reviews each source contribution, clarifies only the affected claim, and reconciles selected mechanisms and metrics after consolidation. This is workflow rationale, not a measured model-quality result.

Visual refinement feedback motivates explicit support for requested portraits, integrated header composition, actual font specimens, functional links and icons, and combining accepted design elements without reopening all choices. These are conditional design procedures. A particular user's photo requirement, serif preference, palette, header arrangement, or number of alternatives is not a universal resume convention. Actual rendering and extraction establish properties of the delivered file; they do not establish hiring effectiveness or universal ATS compatibility.

The bundle contains no renderer or external-service dependency. Content revisions work from supplied facts; formatted outputs use tools available in the host environment. Academic publication CVs have a separate purpose and length convention. Quantitative improvement in resume quality or hiring outcomes remains unmeasured.
