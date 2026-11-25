import { Component, OnDestroy, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { DomSanitizer, SafeUrl } from '@angular/platform-browser';
import { Router } from '@angular/router';
import { LabmindApiService } from '../../services/labmind-api.service';

@Component({
  selector: 'app-accueil',
  imports: [CommonModule],
  templateUrl: './accueil.component.html',
  styleUrl: './accueil.component.css'
})
export class AccueilComponent implements OnDestroy {
  private api = inject(LabmindApiService);
  private router = inject(Router);
  private sanitizer = inject(DomSanitizer);

  selectedFile: File | null = null;
  previewUrl: SafeUrl | null = null;
  private rawObjectUrl: string | null = null;
  isImagePreview = false;
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

  private revokePreview(): void {
    if (this.rawObjectUrl) {
      URL.revokeObjectURL(this.rawObjectUrl);
      this.rawObjectUrl = null;
    }
    this.previewUrl = null;
    this.isImagePreview = false;
  }

  private pickFile(file: File): void {
    this.errorMessage = '';
    const ext = file.name.split('.').pop()?.toLowerCase() || '';
    if (!this.allowedExtensions.includes(ext)) {
      this.revokePreview();
      this.selectedFile = null;
      this.errorMessage = 'Format non supporté. Veuillez choisir un fichier PDF, PNG ou JPG.';
      return;
    }
    if (file.size > this.maxBytes) {
      this.revokePreview();
      this.selectedFile = null;
      this.errorMessage = 'Fichier trop volumineux (maximum 10 Mo).';
      return;
    }

    this.revokePreview();
    this.selectedFile = file;
    if (ext === 'png' || ext === 'jpg' || ext === 'jpeg') {
      this.rawObjectUrl = URL.createObjectURL(file);
      this.previewUrl = this.sanitizer.bypassSecurityTrustUrl(this.rawObjectUrl);
      this.isImagePreview = true;
    } else {
      this.isImagePreview = false;
    }
  }

  clearFile(event: Event): void {
    event.stopPropagation();
    this.revokePreview();
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

  ngOnDestroy(): void {
    this.revokePreview();
  }
}
