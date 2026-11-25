import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'app-telecharger',
  standalone: true,
  imports: [CommonModule, RouterLink],
  template: `
    <section class="dl-wrap">
      <div class="dl-card">
        <h1>Télécharger le projet LabMind</h1>
        <p class="dl-sub">
          L'archive complète contient le backend Python (FastAPI), le frontend Angular et le corpus médical.
        </p>

        @if (status === 'downloading') {
          <p class="dl-status">Préparation du téléchargement de <strong>labmind_projet.zip</strong>…</p>
        } @else if (status === 'done') {
          <p class="dl-status dl-ok">Téléchargement lancé : <strong>labmind_projet.zip</strong></p>
        } @else if (status === 'error') {
          <p class="dl-status dl-err">{{ errorMsg }}</p>
        }

        <div class="dl-actions">
          <button
            type="button"
            class="btn btn-primary"
            (click)="triggerDownload()"
            [disabled]="status === 'downloading'"
          >
            Télécharger labmind_projet.zip
          </button>
          <a routerLink="/" class="btn btn-secondary">← Retour à l'accueil</a>
        </div>
      </div>
    </section>
  `,
  styles: [`
    .dl-wrap {
      max-width: 640px;
      margin: 48px auto;
      padding: 0 20px;
    }
    .dl-card {
      background: #ffffff;
      border: 1px solid #e6dff9;
      border-radius: 18px;
      padding: 32px;
      box-shadow: 0 10px 30px rgba(81, 38, 181, 0.08);
      text-align: center;
    }
    h1 {
      margin: 0 0 10px;
      font-size: 1.5rem;
      color: #1f1738;
    }
    .dl-sub {
      margin: 0 0 20px;
      color: #5b5470;
      line-height: 1.5;
    }
    .dl-status {
      margin: 0 0 20px;
      padding: 10px 14px;
      border-radius: 10px;
      background: #f0ebff;
      color: #5126b5;
      font-size: 0.95rem;
    }
    .dl-ok {
      background: #ecfdf5;
      color: #065f46;
    }
    .dl-err {
      background: #fef2f2;
      color: #991b1b;
    }
    .dl-actions {
      display: flex;
      gap: 12px;
      justify-content: center;
      flex-wrap: wrap;
    }
  `]
})
export class TelechargerComponent implements OnInit {
  status: 'idle' | 'downloading' | 'done' | 'error' = 'idle';
  errorMsg = '';

  ngOnInit(): void {
    void this.triggerDownload();
  }

  async triggerDownload(): Promise<void> {
    if (this.status === 'downloading') return;
    this.status = 'downloading';
    this.errorMsg = '';
    try {
      const resp = await fetch('/labmind_projet.zip', { cache: 'no-store' });
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`);
      }
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'labmind_projet.zip';
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 15000);
      this.status = 'done';
    } catch {
      this.status = 'error';
      this.errorMsg = "Impossible de télécharger l'archive depuis cette fenêtre. Utilisez le bouton Download de Google AI Studio.";
    }
  }
}
