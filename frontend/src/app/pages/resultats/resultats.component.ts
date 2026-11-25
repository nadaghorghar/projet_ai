import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { LabmindApiService } from '../../services/labmind-api.service';
import {
  LabParameter,
  ParameterSummaryStats,
  ResolvedFoodCard,
  formatDisplayCode,
  isPlaceholderLabel,
  isRawCode,
  resolveNutritionHighlights,
  summarizeParameters
} from '../../utils/labmind-view.utils';

@Component({
  selector: 'app-resultats',
  imports: [CommonModule, RouterLink],
  templateUrl: './resultats.component.html',
  styleUrl: './resultats.component.css'
})
export class ResultatsComponent implements OnInit {
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private api = inject(LabmindApiService);

  taskId = '';
  task: any = null;
  pdfUrl = '';
  activeTab: 'anomalies' | 'all' = 'anomalies';
  failedFoodKeys = new Set<string>();
  expandedExplanations = new Set<string>();

  ngOnInit(): void {
    this.taskId = this.route.snapshot.paramMap.get('id') || '';
    if (!this.taskId) {
      this.router.navigate(['/erreur']);
      return;
    }

    this.pdfUrl = this.api.getReportPdfUrl(this.taskId);

    this.api.getTask(this.taskId).subscribe({
      next: (data) => {
        if (data?.status === 'processing' || data?.status === 'received') {
          this.router.navigate(['/attente', this.taskId]);
        } else if (data?.status === 'waiting_for_user') {
          this.router.navigate(['/verification', this.taskId]);
        } else if (data?.status === 'error') {
          const message = data?.errors?.[0]?.message || 'Impossible de traiter ce document.';
          this.router.navigate(['/erreur'], { state: { message } });
        } else {
          this.task = data;
          const stats = this.paramStats;
          this.activeTab = stats.attentionCount > 0 ? 'anomalies' : 'all';
        }
      },
      error: (err) => {
        const formatted = this.api.formatError(err);
        this.router.navigate(['/erreur'], { state: { message: formatted.message } });
      }
    });
  }

  get isImageDoc(): boolean {
    const name: string = this.task?.document?.filename || '';
    return /\.(png|jpe?g)$/i.test(name);
  }

  get paramStats(): ParameterSummaryStats {
    return summarizeParameters(this.task?.parameters || []);
  }

  get displayedParams(): LabParameter[] {
    return this.activeTab === 'anomalies'
      ? this.paramStats.anomalyParams
      : this.paramStats.allParams;
  }

  setTab(tab: 'anomalies' | 'all'): void {
    this.activeTab = tab;
  }

  displayCode(code: string | null | undefined): string {
    return formatDisplayCode(code);
  }

  shouldShowCodeBadge(p: LabParameter): boolean {
    const code = this.displayCode(p.code);
    if (!code) return false;
    return code.toLowerCase() !== String(p.name_printed || '').trim().toLowerCase();
  }

  get generalSummary(): string {
    const apiSummary = String(this.task?.explanations?.general_summary || '').trim();
    if (apiSummary) return apiSummary;

    const stats = this.paramStats;
    const analyzed = stats.allParams.filter(
      (p) => p.status !== 'not_analyzed' && p.status !== 'value_unavailable'
    );
    if (!analyzed.length) {
      return "Aucun paramètre analysable n'a été extrait de ce document.";
    }
    if (stats.normalCount && !stats.attentionCount) {
      return `Les ${stats.normalCount} paramètre(s) mesuré(s) se situent dans les intervalles de référence du laboratoire.`;
    }
    const anomalyNames = stats.anomalyParams
      .slice(0, 4)
      .map((p) => p.name_printed)
      .join(', ');
    const prefix = stats.normalCount
      ? `Sur ${stats.total} paramètre(s) extrait(s), ${stats.normalCount} sont dans les normes du laboratoire. `
      : '';
    return `${prefix}Point(s) à aborder avec votre médecin : ${anomalyNames}.`;
  }

  get orderedConciseExplanations(): Array<{
    code: string;
    codeBadge: string;
    name: string;
    status: string;
    valueText: string;
    normText: string;
    priorNote: string | null;
    markedDeviation: boolean;
    text: string;
    isAnomaly: boolean;
  }> {
    const params: LabParameter[] = this.task?.parameters || [];
    const byCode = new Map<string, LabParameter>();
    for (const p of params) byCode.set(p.code, p);

    const items = (this.task?.explanations?.parameter_explanations || [])
      .filter(
        (e: any) =>
          e?.code &&
          !isRawCode(e.code) &&
          e?.text &&
          e?.status !== 'not_analyzed' &&
          !isPlaceholderLabel(e.text)
      )
      .map((e: any) => {
        const param = byCode.get(e.code);
        const status = param?.status || 'within_reference';
        const isAnomaly = status === 'below_reference' || status === 'above_reference';
        return {
          code: e.code,
          codeBadge: param && this.shouldShowCodeBadge(param) ? this.displayCode(param.code) : '',
          name: param?.name_printed || e.code,
          status,
          valueText: param ? this.formatResult(param) : '—',
          normText: param ? this.formatNorm(param.reference, param.unit) : 'Non fournie',
          priorNote: param?.prior?.note || null,
          markedDeviation: !!param?.marked_deviation,
          text: String(e.text).trim(),
          isAnomaly
        };
      });

    return items.sort((a: any, b: any) => Number(b.isAnomaly) - Number(a.isAnomaly));
  }

  toggleExplanation(code: string): void {
    const next = new Set(this.expandedExplanations);
    if (next.has(code)) {
      next.delete(code);
    } else {
      next.add(code);
    }
    this.expandedExplanations = next;
  }

  isExplanationExpanded(code: string): boolean {
    return this.expandedExplanations.has(code);
  }

  get areAllExplanationsExpanded(): boolean {
    const items = this.orderedConciseExplanations;
    return items.length > 0 && items.every((item) => this.expandedExplanations.has(item.code));
  }

  toggleAllExplanations(): void {
    const items = this.orderedConciseExplanations;
    if (this.areAllExplanationsExpanded) {
      this.expandedExplanations = new Set<string>();
    } else {
      this.expandedExplanations = new Set(items.map((item) => item.code));
    }
  }

  get markedDeviationParams(): LabParameter[] {
    return (this.task?.parameters || []).filter((p: any) => !!p.marked_deviation);
  }

  isUncertainParam(p: LabParameter): boolean {
    return (
      p?.status === 'not_analyzed' ||
      p?.status === 'reference_unavailable' ||
      p?.status === 'value_unavailable'
    );
  }

  formatNumberFr(val: number | null | undefined): string {
    if (val === null || val === undefined) return '—';
    return new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 2 }).format(val);
  }

  formatResult(p: LabParameter): string {
    if (p.value === null || p.value === undefined) return '—';
    const base = `${this.formatNumberFr(p.value)} ${p.unit || ''}`.trim();
    const raw: string = p?.evidence?.raw_text || '';
    const pctMatch = raw.match(/\(\s*\d+(?:[.,]\d+)?\s*%\s*\)/);
    if (pctMatch && p.unit !== '%') {
      return `${base} ${pctMatch[0]}`;
    }
    return base;
  }

  formatNorm(ref: any, unit?: string | null): string {
    if (!ref) return 'Non fournie';
    const u = unit ? ` ${unit}` : '';
    if (ref.min !== null && ref.min !== undefined && ref.max !== null && ref.max !== undefined) {
      return `${this.formatNumberFr(ref.min)} – ${this.formatNumberFr(ref.max)}${u}`;
    }
    if (ref.max !== null && ref.max !== undefined) {
      return `< ${this.formatNumberFr(ref.max)}${u}`;
    }
    if (ref.min !== null && ref.min !== undefined) {
      return `> ${this.formatNumberFr(ref.min)}${u}`;
    }
    return 'Non fournie';
  }

  statusLabel(status: string): string {
    switch (status) {
      case 'within_reference':
        return 'Normal';
      case 'below_reference':
        return 'Bas';
      case 'above_reference':
        return 'Élevé';
      case 'reference_unavailable':
        return 'Réf. absente';
      case 'value_unavailable':
        return 'Valeur absente';
      default:
        return 'Non analysé';
    }
  }

  statusClass(status: string): string {
    switch (status) {
      case 'within_reference':
        return 'status-badge status-ok';
      case 'below_reference':
      case 'above_reference':
        return 'status-badge status-alert';
      default:
        return 'status-badge status-muted';
    }
  }

  get sectionSummaries(): Array<{ title: string; text: string }> {
    return this.task?.explanations?.section_summaries || [];
  }

  get nutritionPlan(): any | null {
    const plan = this.task?.explanations?.nutrition_plan;
    if (plan && plan.status === 'grounded') return plan;
    return null;
  }

  get foodCards(): ResolvedFoodCard[] {
    return resolveNutritionHighlights(this.nutritionPlan?.highlights, this.failedFoodKeys);
  }

  onFoodImageError(key: string): void {
    if (key) {
      const next = new Set(this.failedFoodKeys);
      next.add(key);
      this.failedFoodKeys = next;
    }
  }

  get guidanceSections(): {
    nutrition: string[];
    physical_activity: string[];
    lifestyle_prevention: string[];
  } {
    const g = this.task?.explanations?.guidance_sections || {};
    return {
      nutrition: Array.isArray(g.nutrition) ? g.nutrition : [],
      physical_activity: Array.isArray(g.physical_activity) ? g.physical_activity : [],
      lifestyle_prevention: Array.isArray(g.lifestyle_prevention) ? g.lifestyle_prevention : []
    };
  }

  get lifestyleInfo(): { text: string; isGrounded: boolean } | null {
    const info = this.task?.explanations?.lifestyle_info;
    if (!info?.text) return null;
    return {
      text: info.text,
      isGrounded: info.status === 'grounded'
    };
  }

  get cleanActivityBullets(): string[] {
    return this.guidanceSections.physical_activity.filter((x) => !isPlaceholderLabel(x));
  }

  get cleanPreventionBullets(): string[] {
    return this.guidanceSections.lifestyle_prevention.filter((x) => !isPlaceholderLabel(x));
  }

  get cleanNutritionBullets(): string[] {
    return this.guidanceSections.nutrition.filter((x) => !isPlaceholderLabel(x));
  }

  get hasNutritionSection(): boolean {
    return (
      this.foodCards.length > 0 ||
      !!(this.nutritionPlan?.daily_meal_plan?.length) ||
      this.cleanNutritionBullets.length > 0
    );
  }

  get hasLifestyleHabitsSection(): boolean {
    return (
      this.cleanActivityBullets.length > 0 ||
      this.cleanPreventionBullets.length > 0 ||
      !!(this.lifestyleInfo && this.lifestyleInfo.isGrounded && !isPlaceholderLabel(this.lifestyleInfo.text))
    );
  }

  get consultationQuestions(): string[] {
    return (this.task?.explanations?.consultation_questions || []).filter(
      (q: string) => !isPlaceholderLabel(q)
    );
  }
}
