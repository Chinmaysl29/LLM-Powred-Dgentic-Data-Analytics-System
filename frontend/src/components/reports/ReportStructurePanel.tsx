import React from 'react';
import { CheckSquare, Square, ChevronUp, ChevronDown, Layers, HelpCircle } from 'lucide-react';
import type { ReportSectionConfig } from '../../types/reports';

interface ReportStructurePanelProps {
  sections: ReportSectionConfig[];
  activeSectionId?: string;
  onSelectSection: (sectionId: string) => void;
  onToggleSection: (sectionId: string) => void;
  onMoveUp: (index: number) => void;
  onMoveDown: (index: number) => void;
}

export const ReportStructurePanel: React.FC<ReportStructurePanelProps> = ({
  sections,
  activeSectionId,
  onSelectSection,
  onToggleSection,
  onMoveUp,
  onMoveDown,
}) => {
  const enabledCount = sections.filter((s) => s.enabled).length;

  return (
    <div className="reports-structure-pane">
      <div className="reports-structure-header">
        <div className="reports-structure-title-wrap">
          <Layers size={16} className="reports-pane-icon" />
          <span className="reports-pane-title">Report Structure</span>
        </div>
        <span className="reports-section-count-badge">
          {enabledCount} of {sections.length} active
        </span>
      </div>

      <p className="reports-structure-hint">
        Toggle sections to customize report contents or use reorder arrows to change narrative
        sequence.
      </p>

      {/* Sections List */}
      <div className="reports-structure-list">
        {sections.map((sec, idx) => {
          const isActive = activeSectionId === sec.id;
          const isFirst = idx === 0;
          const isLast = idx === sections.length - 1;

          return (
            <div
              key={sec.id}
              className={`reports-structure-item ${isActive ? 'active' : ''} ${!sec.enabled ? 'disabled' : ''}`}
            >
              {/* Checkbox Toggle */}
              <button
                type="button"
                className="reports-checkbox-btn"
                onClick={() => onToggleSection(sec.id)}
                aria-label={`Toggle section ${sec.title}`}
                title={sec.enabled ? 'Exclude from report' : 'Include in report'}
              >
                {sec.enabled ? (
                  <CheckSquare size={16} className="reports-checkbox-checked" />
                ) : (
                  <Square size={16} className="reports-checkbox-empty" />
                )}
              </button>

              {/* Title click selects / scrolls to section in preview */}
              <div
                className="reports-structure-label-wrap"
                onClick={() => onSelectSection(sec.id)}
                role="button"
                tabIndex={0}
              >
                <span className="reports-structure-name">{sec.title}</span>
                {sec.description && (
                  <span className="reports-structure-desc">{sec.description}</span>
                )}
              </div>

              {/* Reordering Controls */}
              <div className="reports-reorder-group">
                <button
                  type="button"
                  className="reports-reorder-btn"
                  onClick={() => onMoveUp(idx)}
                  disabled={isFirst}
                  title="Move section up"
                  aria-label="Move section up"
                >
                  <ChevronUp size={14} />
                </button>
                <button
                  type="button"
                  className="reports-reorder-btn"
                  onClick={() => onMoveDown(idx)}
                  disabled={isLast}
                  title="Move section down"
                  aria-label="Move section down"
                >
                  <ChevronDown size={14} />
                </button>
              </div>
            </div>
          );
        })}
      </div>

      <div className="reports-structure-footer">
        <HelpCircle size={13} />
        <span>Sections with checked boxes appear in the generated document and PDF export.</span>
      </div>
    </div>
  );
};
