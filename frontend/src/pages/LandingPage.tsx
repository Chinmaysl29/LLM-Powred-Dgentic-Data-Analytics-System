import { Link } from 'react-router-dom';
import { ArrowRight, Database, ChartNoAxesCombined, FileText } from 'lucide-react';

export default function LandingPage() {
  return (
    <div className="product-home">
      <a href="#main-content" className="product-skip">Skip to main content</a>
      <header className="product-header">
        <Link to="/" className="product-brand"><img src="/favicon.svg" width="30" height="30" alt="" />AI Data Analyst OS</Link>
        <nav aria-label="Main navigation">
          <a href="#workflow">Workflow</a>
          <Link to="/login">Log in</Link>
          <Link to="/signup" className="product-button product-button--primary">Create account</Link>
        </nav>
      </header>
      <main id="main-content" tabIndex={-1}>
        <section className="product-intro" aria-labelledby="product-heading">
          <div>
            <p className="product-eyebrow">Your analytics workspace</p>
            <h1 id="product-heading">Start with your data.<br />Understand the result.</h1>
            <p className="product-description">Upload datasets, ask questions, and review the tables, charts, and SQL behind your analysis in one workspace.</p>
            <div className="product-actions">
              <Link to="/datasets" className="product-button product-button--primary">Open workspace <ArrowRight size={17} aria-hidden="true" /></Link>
              <a href="#workflow" className="product-button">Explore the workflow</a>
            </div>
            <p className="product-note">Use your own datasets. Review analytical outputs before making decisions.</p>
          </div>
          <aside className="product-start" aria-label="Getting started">
            <p className="product-eyebrow">A clear starting point</p>
            <h2>Bring a question and a dataset.</h2>
            <ol>
              <li><strong>Upload and inspect</strong><span>Check columns, data types, and preview rows.</span></li>
              <li><strong>Ask and explore</strong><span>Select a dataset and submit an analytical question.</span></li>
              <li><strong>Review and share</strong><span>Inspect results and prepare a report.</span></li>
            </ol>
            <Link to="/datasets/upload">Upload a dataset <ArrowRight size={16} aria-hidden="true" /></Link>
          </aside>
        </section>
        <section id="workflow" className="product-workflow" aria-labelledby="workflow-heading">
          <p className="product-eyebrow">From source to result</p>
          <h2 id="workflow-heading">Keep the analysis connected.</h2>
          <div className="product-feature-grid">
            <article><Database size={24} aria-hidden="true" /><h3>Dataset management</h3><p>Upload files and inspect their structure before starting an analysis.</p><Link to="/datasets">View datasets <ArrowRight size={16} aria-hidden="true" /></Link></article>
            <article><ChartNoAxesCombined size={24} aria-hidden="true" /><h3>Analysis workspace</h3><p>Ask questions about a selected dataset and inspect the returned evidence.</p><Link to="/analysis">Open analysis <ArrowRight size={16} aria-hidden="true" /></Link></article>
            <article><FileText size={24} aria-hidden="true" /><h3>Reports</h3><p>Organize analytical findings into reports you can revisit and download.</p><Link to="/reports">View reports <ArrowRight size={16} aria-hidden="true" /></Link></article>
          </div>
        </section>
      </main>
      <footer className="product-footer"><span>AI Data Analyst OS</span><nav aria-label="Legal"><Link to="/privacy">Privacy policy</Link><Link to="/terms">Terms</Link></nav></footer>
    </div>
  );
}
