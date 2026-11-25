import { Component, OnInit, OnDestroy, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router } from '@angular/router';
import { Subscription, interval, switchMap, startWith } from 'rxjs';
import { LabmindApiService } from '../../services/labmind-api.service';
import { LOADING_MESSAGES, computeLoadingStage } from '../../utils/labmind-view.utils';

@Component({
  selector: 'app-attente',
  imports: [CommonModule],
  templateUrl: './attente.component.html',
  styleUrl: './attente.component.css'
})
export class AttenteComponent implements OnInit, OnDestroy {
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private api = inject(LabmindApiService);

  taskId = '';
  filename = 'Votre document';
  stageIndex = 0;
  progressPercent = 18;
  activeMessage = LOADING_MESSAGES[0];
  elapsedSeconds = 0;
  private latestTask: any = null;
  private pollSub: Subscription | null = null;
  private timerSub: Subscription | null = null;

  readonly stages = LOADING_MESSAGES;

  private updateProgress(): void {
    const info = computeLoadingStage(this.latestTask, this.elapsedSeconds);
    this.stageIndex = info.stageIndex;
    this.progressPercent = info.progressPercent;
    this.activeMessage = info.activeMessage;
  }

  ngOnInit(): void {
    this.taskId = this.route.snapshot.paramMap.get('id') || '';
    if (!this.taskId) {
      this.router.navigate(['/erreur']);
      return;
    }

    this.timerSub = interval(1000).subscribe(() => {
      this.elapsedSeconds++;
      this.updateProgress();
    });

    this.pollSub = interval(2000)
      .pipe(
        startWith(0),
        switchMap(() => this.api.getTask(this.taskId))
      )
      .subscribe({
        next: (task) => {
          this.latestTask = task;
          if (task?.document?.filename) {
            this.filename = task.document.filename;
          }
          this.updateProgress();

          if (task?.status === 'waiting_for_user') {
            this.stopTimers();
            this.router.navigate(['/verification', this.taskId]);
          } else if (task?.status === 'done') {
            this.stopTimers();
            this.router.navigate(['/resultats', this.taskId]);
          } else if (task?.status === 'error') {
            this.stopTimers();
            const message =
              task?.errors?.[0]?.message || 'Impossible de traiter ce document.';
            this.router.navigate(['/erreur'], { state: { message } });
          }
        },
        error: (err) => {
          this.stopTimers();
          const formatted = this.api.formatError(err);
          this.router.navigate(['/erreur'], { state: { message: formatted.message } });
        }
      });
  }

  private stopTimers(): void {
    this.pollSub?.unsubscribe();
    this.timerSub?.unsubscribe();
  }

  cancelAndReturn(): void {
    this.stopTimers();
    this.api.deleteTask(this.taskId).subscribe({
      next: () => this.router.navigate(['/']),
      error: () => this.router.navigate(['/'])
    });
  }

  ngOnDestroy(): void {
    this.stopTimers();
  }
}
