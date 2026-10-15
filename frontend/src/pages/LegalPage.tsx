import { Link } from 'react-router-dom';

const privacy = [
  ['Operator and contact', 'Owner review required: identify the legal operator, its address, privacy contact, and request channel before publication. These details have not been supplied.'],
  ['Information processed', 'The application accepts account details, uploaded datasets and documents, analytical questions, and generated results. The backend includes database storage, file storage, audit logging, usage counters, and optional conversation memory. Dataset contents may include personal information; upload only information you are authorized to process.'],
  ['Purpose and uploaded data', 'Uploaded content is used for dataset parsing, profiling, retrieval, analysis, and requested outputs. The deployed operator must confirm which features are enabled, the purposes and legal basis for processing, and whether any additional use is made of this information.'],
  ['AI and third-party processors', 'The code supports configurable Groq, Google Gemini, OpenAI, embedding, database, and hosting services. Which providers receive content depends on the deployment and requested workflow. Owner review required: publish the actual processor list, what each receives, its terms, processing locations, and any international transfer safeguards. No claim about provider training or retention is made here.'],
  ['Storage and retention', 'The implementation can store uploads, processed data, reports, dashboards, memory, and logs. Retention periods, backup deletion, and account-wide deletion guarantees have not been established. Deleting a dataset must not be assumed to erase all derived records or backups. Owner review required: document and verify the full retention and deletion schedule.'],
  ['Browser storage and analytics', 'The frontend stores a sign-in token and some interface preferences in browser local storage. The backend includes operational metrics and usage-event functionality. Owner review required: verify deployed tracking, cookies, consent requirements, and access logging. This draft does not assert that tracking is absent.'],
  ['Rights, requests, and sharing', 'The operator must provide a verified way to request access, correction, export, or deletion where applicable, and disclose recipients and any required sharing. Those procedures and contacts remain unconfirmed.'],
  ['Updates', 'Draft prepared for implementation review on 11 October 2026. No effective policy date has been approved. The operator must approve the final notice and explain how material changes will be communicated.'],
];

const terms = [
  ['Operator, eligibility, and agreement', 'Owner/legal review required: identify the contracting entity, contact address, eligibility requirements, and acceptance mechanism. This page is an unpublished draft for review, not an approved customer agreement.'],
  ['Service', 'AI Data Analyst OS provides interfaces for uploading datasets, requesting analysis, exploring results, and using configured forecasting and reporting services. Availability depends on the deployment and enabled integrations. Features marked unavailable are not represented as working services.'],
  ['Accounts and acceptable use', 'Proposed terms for review: users should protect account credentials, provide accurate registration details, and avoid unlawful use, unauthorized access, harmful uploads, or attempts to disrupt service. The operator must approve the final obligations and enforcement process.'],
  ['Uploaded content and intellectual property', 'Owner/legal review required: define ownership of uploaded content, the limited permissions required to process it, responsibility for obtaining data rights, ownership or licensing of outputs, and permitted use of product software and branding. No transfer of ownership is asserted by this draft.'],
  ['Analytical output and forecasts', 'AI-generated answers, forecasts, and recommendations may be incomplete or incorrect. Review source data, assumptions, and available validation metrics before relying on results. Model confidence is not a guarantee. Outputs should not be treated as professional advice or a promise of business performance.'],
  ['Third-party services and availability', 'Configured hosting, AI, and data services may have separate terms and limitations. No uptime, response-time, or accuracy commitment has been supplied. Owner/legal review required: identify applicable third-party terms, support arrangements, and any service commitments.'],
  ['Liability, suspension, and termination', 'Owner/legal review required: draft jurisdiction-appropriate liability provisions, suspension criteria, notice and appeal procedures, termination rights, and access to or deletion of stored data. These terms must be approved before launch.'],
  ['Law, disputes, contact, and effective date', 'Governing law, dispute process, contracting entity, contact channel, and effective date are unresolved. Draft prepared on 11 October 2026 for owner/legal review. Public launch remains blocked until approved.'],
];

export default function LegalPage({ kind }: { kind: 'privacy' | 'terms' }) {
  const title = kind === 'privacy' ? 'Privacy Policy' : 'Terms and Conditions';
  const sections = kind === 'privacy' ? privacy : terms;
  return <main className="page-container" style={{ maxWidth: 860, margin: '0 auto', padding: '32px 24px', lineHeight: 1.7 }}>
    <nav aria-label="Legal navigation"><Link to="/">AI Data Analyst OS</Link>{' / '}<Link to="/privacy">Privacy</Link>{' / '}<Link to="/terms">Terms</Link></nav>
    <h1>{title}</h1>
    <p role="note"><strong>Draft — awaiting owner and legal review.</strong> Required business facts are unresolved. This document is not approved for production publication.</p>
    <nav aria-label="On this page"><ol>{sections.map(([heading], index) => <li key={heading}><a href={`#section-${index}`}>{heading}</a></li>)}</ol></nav>
    {sections.map(([heading, body], index) => <section key={heading} id={`section-${index}`} style={{ marginTop: 28 }}><h2 style={{ fontSize: 20 }}>{heading}</h2><p>{body}</p></section>)}
    <footer><Link to="/login">Back to sign in</Link></footer>
  </main>;
}
