import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { LabmindApiService } from '../../services/labmind-api.service';

const NFS_CORE_CODES = new Set(['RBC', 'HGB', 'HCT', 'VGM', 'TCMH', 'CCMH', 'WBC', 'PLT']);
const LEUKOCYTE_CODES = new Set(['NEUT', 'LYMPH', 'MONO', 'EOS', 'BASO']);

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
  isDeleting = false;
  deleted = false;
  errorMessage = '';

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

  get nfsCoreParams(): any[] {
    return (this.task?.parameters || []).filter((p: any) => NFS_CORE_CODES.has(p.code));
  }

  get leukocyteParams(): any[] {
    return (this.task?.parameters || []).filter((p: any) => LEUKOCYTE_CODES.has(p.code));
  }

  get biochemParams(): any[] {
    return (this.task?.parameters || []).filter(
      (p: any) => !NFS_CORE_CODES.has(p.code) && !LEUKOCYTE_CODES.has(p.code)
    );
  }

  get allLeukocytesWithinRef(): boolean {
    return (
      this.leukocyteParams.length > 0 &&
      this.leukocyteParams.every((p: any) => p.status === 'within_reference')
    );
  }

  get hasBiochemAttention(): boolean {
    return this.biochemParams.some(
      (p: any) => p.status === 'below_reference' || p.status === 'above_reference'
    );
  }

  formatNumberFr(val: number | null | undefined): string {
    if (val === null || val === undefined) return '—';
    return new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 2 }).format(val);
  }

  formatResult(p: any): string {
    if (p.value === null || p.value === undefined) return '—';
    const base = `${this.formatNumberFr(p.value)} ${p.unit || ''}`.trim();
    const raw: string = p?.evidence?.raw_text || '';
    const pctMatch = raw.match(/\(\s*\d+(?:[.,]\d+)?\s*%\s*\)/);
    if (pctMatch && p.unit !== '%') {
      return `${base} ${pctMatch[0]}`;
    }
    return base;
  }

  formatNorm(ref: any, unit?: string): string {
    if (!ref) return 'Non fournie';
    const u = unit ? ` ${unit}` : '';
    if (ref.min !== null && ref.min !== undefined && ref.max !== null && ref.max !== undefined) {
      return `${this.formatNumberFr(ref.min)} - ${this.formatNumberFr(ref.max)}${u}`;
    }
    if (ref.max !== null && ref.max !== undefined) {
      return `Inférieur à ${this.formatNumberFr(ref.max)}${u}`;
    }
    if (ref.min !== null && ref.min !== undefined) {
      return `Supérieur à ${this.formatNumberFr(ref.min)}${u}`;
    }
    return 'Non fournie';
  }

  formatNormCard(ref: any, unit?: string): string {
    if (!ref) return 'Norme non fournie';
    const u = unit ? ` ${unit}` : '';
    if (ref.min !== null && ref.min !== undefined && ref.max !== null && ref.max !== undefined) {
      return `Norme : ${this.formatNumberFr(ref.min)} à ${this.formatNumberFr(ref.max)}${u}`;
    }
    if (ref.max !== null && ref.max !== undefined) {
      return `Norme : < ${this.formatNumberFr(ref.max)}${u}`;
    }
    if (ref.min !== null && ref.min !== undefined) {
      return `Norme : > ${this.formatNumberFr(ref.min)}${u}`;
    }
    return 'Norme non fournie';
  }

  statusLabel(status: string): string {
    switch (status) {
      case 'within_reference':
        return 'Normal';
      case 'below_reference':
        return '▲ Légèrement bas';
      case 'above_reference':
        return '▲ Élevé';
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
        return 'status-ok';
      case 'below_reference':
      case 'above_reference':
        return 'status-alert';
      default:
        return 'status-muted';
    }
  }

  explanationFor(code: string): string {
    const items = this.task?.explanations?.parameter_explanations || [];
    const found = items.find((e: any) => e?.code === code && e?.status === 'grounded' && e?.text);
    if (found) return found.text;
    const anyFound = items.find((e: any) => e?.code === code && e?.text);
    return anyFound ? anyFound.text : '';
  }

  get sectionSummaries(): Array<{ title: string; text: string }> {
    return this.task?.explanations?.section_summaries || [];
  }

  get nutritionPlan(): any | null {
    const plan = this.task?.explanations?.nutrition_plan;
    if (plan && plan.status === 'grounded') return plan;
    return null;
  }

  get lifestyleInfo(): { text: string; isGrounded: boolean } | null {
    const info = this.task?.explanations?.lifestyle_info;
    if (!info?.text) return null;
    return {
      text: info.text,
      isGrounded: info.status === 'grounded'
    };
  }

  get actionSteps(): string[] {
    return this.task?.explanations?.action_steps || [];
  }

  get consultationQuestions(): string[] {
    return this.task?.explanations?.consultation_questions || [];
  }

  foodImagePath(key: string): string {
    switch (key) {
      case 'almonds_walnuts':
        return 'assets/foods/almonds_walnuts.jpg';
      case 'pumpkin_seeds':
        return 'assets/foods/pumpkin_seeds.jpg';
      case 'spinach':
        return 'assets/foods/spinach.jpg';
      case 'lentils_chickpeas':
        return 'assets/foods/lentils_chickpeas.jpg';
      default:
        return 'assets/foods/lentils_chickpeas.jpg';
    }
  }

  deleteData(): void {
    if (this.isDeleting) return;
    this.isDeleting = true;
    this.errorMessage = '';
    this.api.deleteTask(this.taskId).subscribe({
      next: () => {
        this.isDeleting = false;
        this.deleted = true;
      },
      error: (err) => {
        this.isDeleting = false;
        this.errorMessage = this.api.formatError(err).message;
      }
    });
  }
}
