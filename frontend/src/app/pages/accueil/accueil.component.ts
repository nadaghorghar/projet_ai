import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { LabmindApiService } from '../../services/labmind-api.service';

@Component({
  selector: 'app-accueil',
  imports: [CommonModule],
  templateUrl: './accueil.component.html',
  styleUrl: './accueil.component.css'
})
export class AccueilComponent {
  private api = inject(LabmindApiService);
  private router = inject(Router);

  selectedFile: File | null = null;
  errorMessage = '';
  isDragging = false;
  isUploading = false;

  private readonly allowedExtensions = ['pdf', 'png', 'jpg', 'jpeg'];
  private readonly maxBytes = 10 * 1024 * 1024;

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (file) {
      this.pickFile(file);
    }
    input.value = '';
  }

  onDragOver(event: DragEvent): void {
    event.preventDefault();
    this.isDragging = true;
  }

  onDragLeave(): void {
    this.isDragging = false;
  }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    this.isDragging = false;
    const file = event.dataTransfer?.files?.[0];
    if (file) {
      this.pickFile(file);
    }
  }

  private pickFile(file: File): void {
    this.errorMessage = '';
    const ext = file.name.split('.').pop()?.toLowerCase() || '';

    if (!this.allowedExtensions.includes(ext)) {
      this.selectedFile = null;
      this.errorMessage = 'Format non supporté. Veuillez choisir un fichier PDF, PNG ou JPG.';
      return;
    }

    if (file.size > this.maxBytes) {
      this.selectedFile = null;
      this.errorMessage = 'Fichier trop volumineux (maximum 10 Mo).';
      return;
    }

    this.selectedFile = file;
  }

  clearFile(event: Event): void {
    event.stopPropagation();
    this.selectedFile = null;
    this.errorMessage = '';
  }

  formatSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} o`;
    if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} Ko`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
  }

  onSubmit(fileInput: HTMLInputElement): void {
    if (!this.selectedFile) {
      fileInput.click();
      return;
    }

    if (this.isUploading) return;

    this.errorMessage = '';
    this.isUploading = true;

    this.api.createTask(this.selectedFile).subscribe({
      next: (task) => {
        this.isUploading = false;
        if (task?.status === 'done') {
          this.router.navigate(['/resultats', task.task_id]);
        } else if (task?.status === 'waiting_for_user') {
          this.router.navigate(['/verification', task.task_id]);
        } else {
          this.router.navigate(['/attente', task.task_id]);
        }
      },
      error: (err) => {
        this.isUploading = false;
        this.errorMessage = this.api.formatError(err).message;
      }
    });
  }
}
