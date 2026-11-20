import { Component, OnInit, OnDestroy, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router } from '@angular/router';
import { Subscription, interval, switchMap, startWith } from 'rxjs';
import { LabmindApiService } from '../../services/labmind-api.service';

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
  private pollSub: Subscription | null = null;

  ngOnInit(): void {
    this.taskId = this.route.snapshot.paramMap.get('id') || '';
    if (!this.taskId) {
      this.router.navigate(['/erreur']);
      return;
    }

    this.pollSub = interval(2000)
      .pipe(
        startWith(0),
        switchMap(() => this.api.getTask(this.taskId))
      )
      .subscribe({
        next: (task) => {
          if (task?.document?.filename) {
            this.filename = task.document.filename;
          }

          if (task?.status === 'waiting_for_user') {
            this.pollSub?.unsubscribe();
            this.router.navigate(['/verification', this.taskId]);
          } else if (task?.status === 'done') {
            this.pollSub?.unsubscribe();
            this.router.navigate(['/resultats', this.taskId]);
          } else if (task?.status === 'error') {
            this.pollSub?.unsubscribe();
            const message =
              task?.errors?.[0]?.message || 'Impossible de traiter ce document.';
            this.router.navigate(['/erreur'], { state: { message } });
          }
        },
        error: (err) => {
          this.pollSub?.unsubscribe();
          const formatted = this.api.formatError(err);
          this.router.navigate(['/erreur'], { state: { message: formatted.message } });
        }
      });
  }

  cancelAndDelete(): void {
    this.pollSub?.unsubscribe();
    this.api.deleteTask(this.taskId).subscribe({
      next: () => this.router.navigate(['/']),
      error: () => this.router.navigate(['/'])
    });
  }

  ngOnDestroy(): void {
    this.pollSub?.unsubscribe();
  }
}
