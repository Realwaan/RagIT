import { useState, type FormEvent } from 'react';
import { Plus, Sparkles, Trash2 } from 'lucide-react';
import type { CustomCheckDraft } from '../types';
import { IconButton } from './ui';

type Props = {
  customChecks: CustomCheckDraft[];
  loading: boolean;
  onRunAudit: () => void;
  onAddRule: (draft: Omit<CustomCheckDraft, 'id'>) => void;
  onRemoveRule: (id: string) => void;
};

export function CustomRulesBuilder({
  customChecks,
  loading,
  onRunAudit,
  onAddRule,
  onRemoveRule,
}: Props) {
  const [newTitle, setNewTitle] = useState('');
  const [newQuery, setNewQuery] = useState('');
  const [newTerms, setNewTerms] = useState('');
  const [newCriticality, setNewCriticality] = useState<'CRITICAL' | 'HIGH' | 'MEDIUM'>('HIGH');
  const [newClause, setNewClause] = useState('');

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    const title = newTitle.trim();
    const query = newQuery.trim();
    if (!title || !query) return;
    const terms = newTerms
      .split(',')
      .map(t => t.trim().toLowerCase())
      .filter(Boolean);
    onAddRule({
      title,
      query,
      category: 'Custom Control',
      criticality: newCriticality,
      required_terms: terms,
      standard_clause: newClause.trim() || undefined,
      action_required: `Ensure ${title} requirement is explicitly addressed in the agreement.`,
    });
    setNewTitle('');
    setNewQuery('');
    setNewTerms('');
    setNewClause('');
  };

  return (
    <section className="custom-rules-box" aria-label="Custom compliance rules">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <div>
          <h3 className="text-sm font-semibold">Custom checklist rules ({customChecks.length})</h3>
          <p className="muted text-xs">
            Each rule retrieves relevant clauses and verifies required control terms.
          </p>
        </div>
        <button
          type="button"
          className="primary flex items-center gap-1.5 text-xs"
          disabled={loading || !customChecks.length}
          onClick={onRunAudit}
        >
          <Sparkles size={14} />
          <span>{loading ? 'Running custom audit…' : 'Run custom audit'}</span>
        </button>
      </div>

      <div className="custom-rule-list">
        {customChecks.map(rule => (
          <div key={rule.id} className="custom-rule-item">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="audit-badge-neutral">{rule.id}</span>
                <strong className="text-xs font-semibold">{rule.title}</strong>
                <span className="muted text-xs">({rule.criticality})</span>
              </div>
              <p className="muted text-xs mt-1 truncate">{rule.query}</p>
            </div>
            <IconButton label={`Remove ${rule.title}`} onClick={() => onRemoveRule(rule.id)}>
              <Trash2 size={14} />
            </IconButton>
          </div>
        ))}
      </div>

      <form className="custom-rule-form" onSubmit={handleSubmit}>
        <input
          className="text-field"
          placeholder="Control title (e.g., Data Encryption at Rest)"
          aria-label="Custom control title"
          value={newTitle}
          onChange={e => setNewTitle(e.target.value)}
        />
        <input
          className="text-field"
          placeholder="Audit question (e.g., How is customer data encrypted at rest?)"
          aria-label="Custom control question"
          value={newQuery}
          onChange={e => setNewQuery(e.target.value)}
        />
        <div className="grid grid-cols-3 gap-2">
          <input
            className="text-field col-span-2"
            placeholder="Required terms, comma-separated (e.g., aes-256, encryption)"
            aria-label="Required control terms"
            value={newTerms}
            onChange={e => setNewTerms(e.target.value)}
          />
          <select
            className="text-field"
            aria-label="Custom control criticality"
            value={newCriticality}
            onChange={e => setNewCriticality(e.target.value as 'CRITICAL' | 'HIGH' | 'MEDIUM')}
          >
            <option value="CRITICAL">CRITICAL</option>
            <option value="HIGH">HIGH</option>
            <option value="MEDIUM">MEDIUM</option>
          </select>
        </div>
        <div className="flex gap-2">
          <input
            className="text-field flex-1"
            placeholder="Optional standard remediation clause"
            aria-label="Standard remediation clause"
            value={newClause}
            onChange={e => setNewClause(e.target.value)}
          />
          <button
            type="submit"
            className="secondary flex items-center gap-1 shrink-0"
            disabled={!newTitle.trim() || !newQuery.trim()}
          >
            <Plus size={15} /> Add rule
          </button>
        </div>
      </form>
    </section>
  );
}
