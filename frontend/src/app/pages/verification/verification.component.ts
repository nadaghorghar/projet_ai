import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { LabmindApiService } from '../../services/labmind-api.service';

@Component({
  selector: 'app-verification',
  imports: [CommonModule, FormsModule],
  templateUrl: './verification.component.html',
  styleUrl: './verification.component.css'
})
export class VerificationComponent implements OnInit {
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private api = inject(LabmindApiService);

  taskId = '';
  filename = 'Votre document';
  question: any = null;
  selectedOption = '';
  customValue = '';
  errorMessage = '';
  isSubmitting = false;

  ngOnInit(): void {
    this.taskId = this.route.snapshot.paramMap.get('id') || '';
    if (!this.taskId) {
      this.router.navigate(['/erreur']);
      return;
    }

    this.api.getTask(this.taskId).subscribe({
      next: (task) => {
        if (task?.document?.filename) {
          this.filename = task.document.filename;
        }
        if (task?.status === 'done') {
          this.router.navigate(['/resultats', this.taskId]);
        } else if (task?.status === 'processing' || task?.status === 'received') {
          this.router.navigate(['/attente', this.taskId]);
        } else if (task?.status === 'error') {
          const message = task?.errors?.[0]?.message || 'Impossible de poursuivre.';
          this.router.navigate(['/erreur'], { state: { message } });
        } else {
          this.question = task?.pending_question || null;
        }
      },
      error: (err) => {
        const formatted = this.api.formatError(err);
        this.router.navigate(['/erreur'], { state: { message: formatted.message } });
      }
    });
  }

  get options(): string[] {
    const raw: string[] = this.question?.options || [];
    if (raw.includes('je ne sais pas')) {
      return raw;
    }
    return [...raw, 'je ne sais pas'];
  }

  chooseAndSend(option: string): void {
    if (option === 'autre') {
      this.selectedOption = 'autre';
      this.errorMessage = '';
      return;
    }
    this.selectedOption = option;
    this.send(option);
  }

  submitCustom(): void {
    const trimmed = this.customValue.trim();
    if (!trimmed) {
      this.errorMessage = 'Veuillez saisir la valeur indiquée sur votre document.';
      return;
    }
    this.send(trimmed);
  }

  private send(answer: string): void {
    if (!this.question || this.isSubmitting) return;
    this.isSubmitting = true;
    this.errorMessage = '';

    this.api.submitAnswer(this.taskId, this.question.question_id, answer).subscribe({
      next: (task) => {
        this.isSubmitting = false;
        if (task?.status === 'done') {
          this.router.navigate(['/resultats', this.taskId]);
        } else if (task?.status === 'waiting_for_user') {
          this.question = task.pending_question;
          this.selectedOption = '';
          this.customValue = '';
        } else if (task?.status === 'error') {
          const message = task?.errors?.[0]?.message || 'Erreur lors du traitement.';
          this.router.navigate(['/erreur'], { state: { message } });
        } else {
          this.router.navigate(['/attente', this.taskId]);
        }
      },
      error: (err) => {
        this.isSubmitting = false;
        this.errorMessage = this.api.formatError(err).message;
      }
    });
  }
}
