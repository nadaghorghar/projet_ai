import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, of, throwError, delay } from 'rxjs';

@Injectable({
  providedIn: 'root'
})
export class LabmindApiService {
  private http = inject(HttpClient);

  // Branché sur le backend FastAPI réel (lancer Angular sur --port 5173)
  readonly useMock = false;
  readonly apiUrl = 'http://127.0.0.1:8000/v1';

  private mockPollCount = 0;
  private mockAnsweredUnit: string | null = null;
  private mockDeleted = false;
  private mockFilename = 'bilan_sang.pdf';

  private readonly mockDisclaimer =
    'Outil pédagogique : ce bilan ne remplace pas une consultation médicale et ne constitue ni un diagnostic ni une prescription.';

  // GET /v1/health
  checkHealth(): Observable<any> {
    if (!this.useMock) {
      return this.http.get(`${this.apiUrl}/health`);
    }
    return of({ status: 'ok' });
  }

  // POST /v1/tasks
  createTask(file: File): Observable<any> {
    if (!this.useMock) {
      const formData = new FormData();
      formData.append('file', file);
      return this.http.post(`${this.apiUrl}/tasks`, formData);
    }

    const ext = file.name.split('.').pop()?.toLowerCase() || '';
    if (!['pdf', 'png', 'jpg', 'jpeg'].includes(ext)) {
      return throwError(() => ({
        status: 415,
        error: {
          error: {
            code: 'unsupported_format',
            message: 'Format non supporté (pdf, png, jpg, jpeg).'
          }
        }
      })).pipe(delay(300));
    }

    if (file.size > 10 * 1024 * 1024) {
      return throwError(() => ({
        status: 413,
        error: {
          error: {
            code: 'file_too_large',
            message: 'Le fichier dépasse la taille maximale autorisée (10 Mo).'
          }
        }
      })).pipe(delay(300));
    }

    this.mockPollCount = 0;
    this.mockAnsweredUnit = null;
    this.mockDeleted = false;
    this.mockFilename = file.name;

    return of({
      task_id: '3f2b8c1e-6a52-4d7e-9a0c-1b2d3e4f5a6b',
      status: 'received',
      document: { filename: this.mockFilename, extraction_method: null },
      detected_categories: [],
      parameters: [],
      pending_question: null,
      report_id: null,
      explanations: null,
      sources: [],
      disclaimer: this.mockDisclaimer,
      errors: []
    }).pipe(delay(350));
  }

  // GET /v1/tasks/{task_id}
  getTask(taskId: string): Observable<any> {
    if (!this.useMock) {
      return this.http.get(`${this.apiUrl}/tasks/${taskId}`);
    }

    if (this.mockDeleted) {
      return throwError(() => ({
        status: 404,
        error: {
          error: {
            code: 'task_not_found',
            message: 'Tâche introuvable ou supprimée.'
          }
        }
      }));
    }

    this.mockPollCount++;

    if (this.mockPollCount === 1) {
      return of({
        task_id: taskId,
        status: 'processing',
        document: { filename: this.mockFilename, extraction_method: null },
        detected_categories: [],
        parameters: [],
        pending_question: null,
        report_id: null,
        explanations: null,
        sources: [],
        disclaimer: this.mockDisclaimer,
        errors: []
      });
    }

    if (this.mockPollCount === 2 && this.mockAnsweredUnit === null) {
      return of({
        task_id: taskId,
        status: 'waiting_for_user',
        document: { filename: this.mockFilename, extraction_method: 'pdf_text' },
        detected_categories: ['NFS'],
        parameters: [],
        pending_question: {
          question_id: 'q-001',
          field: 'unit',
          code: 'HCT',
          message:
            "L'unité de l'hématocrite est absente du document. Quelle unité figure sur votre compte rendu ?",
          options: ['%', 'autre', 'je ne sais pas']
        },
        report_id: null,
        explanations: null,
        sources: [],
        disclaimer: this.mockDisclaimer,
        errors: []
      });
    }

    return of({
      task_id: taskId,
      status: 'done',
      document: { filename: this.mockFilename, extraction_method: 'pdf_text' },
      detected_categories: ['NFS'],
      parameters: [
        {
          code: 'HGB',
          name_printed: 'Hémoglobine',
          value: 13.5,
          unit: 'g/dL',
          reference: { min: 12.0, max: 16.0, origin: 'document_laboratoire' },
          status: 'within_reference',
          reason: null,
          confidence: 0.96,
          evidence: { raw_text: 'Hémoglobine 13,5 g/dL 12,0 - 16,0', page: 1 }
        },
        {
          code: 'WBC',
          name_printed: 'Globules blancs',
          value: 11.2,
          unit: 'G/L',
          reference: { min: 4.0, max: 10.0, origin: 'document_laboratoire' },
          status: 'above_reference',
          reason: null,
          confidence: 0.95,
          evidence: { raw_text: 'Globules blancs 11,2 G/L 4,0 - 10,0', page: 1 }
        }
      ],
      pending_question: null,
      report_id: 'r-3f2b8c1e',
      explanations: {
        summary: 'Explications pédagogiques produites exclusivement à partir des sources documentaires vérifiées.',
        parameter_explanations: [
          {
            code: 'WBC',
            status: 'grounded',
            text: "Les globules blancs (leucocytes) participent aux défenses de l'organisme. Une valeur supérieure à la fourchette du laboratoire justifie d'en parler lors d'une consultation médicale.",
            source_ids: ['ameli-prise-sang-2026']
          }
        ],
        lifestyle_info: {
          status: 'grounded',
          text: "Une alimentation variée, une hydratation régulière et un sommeil suffisant contribuent au bon équilibre général, selon les repères publics de l'ANSES.",
          source_ids: ['anses-reperes-2026']
        },
        consultation_questions: [
          'Cette valeur de globules blancs nécessite-t-elle un contrôle ultérieur ?',
          'Y a-t-il des éléments cliniques à prendre en compte avec ces résultats ?'
        ]
      },
      sources: [
        {
          source_id: 'ameli-prise-sang-2026',
          title: "Comment lire les résultats d'une prise de sang ?",
          organisme: 'Assurance Maladie (ameli.fr)',
          url: 'https://www.ameli.fr/assure/sante/examen/analyse/lire-resultats-prise-sang',
          date: '2026-01-08'
        }
      ],
      disclaimer: this.mockDisclaimer,
      errors: []
    });
  }

  // POST /v1/tasks/{task_id}/answer
  submitAnswer(taskId: string, questionId: string, answer: string): Observable<any> {
    if (!this.useMock) {
      return this.http.post(`${this.apiUrl}/tasks/${taskId}/answer`, {
        question_id: questionId,
        answer
      });
    }
    this.mockAnsweredUnit = answer.trim();
    return this.getTask(taskId).pipe(delay(300));
  }

  // GET /v1/tasks/{task_id}/report.pdf
  getReportPdfUrl(taskId: string): string {
    return `${this.apiUrl}/tasks/${taskId}/report.pdf`;
  }

  // DELETE /v1/tasks/{task_id}
  deleteTask(taskId: string): Observable<void> {
    if (!this.useMock) {
      return this.http.delete<void>(`${this.apiUrl}/tasks/${taskId}`);
    }
    this.mockDeleted = true;
    return of(void 0).pipe(delay(250));
  }

  // Extraire { code, message } selon {"error": {"code", "message"}}
  formatError(err: any): { code: string; message: string } {
    const apiErr = err?.error?.error;
    if (apiErr?.code && apiErr?.message) {
      return { code: apiErr.code, message: apiErr.message };
    }
    if (err?.status === 0) {
      return {
        code: 'connection_refused',
        message:
          "Impossible de joindre le serveur backend sur http://127.0.0.1:8000. Vérifiez qu'uvicorn est démarré."
      };
    }
    return {
      code: 'internal_error',
      message: 'Une erreur technique est survenue lors de la communication avec le serveur.'
    };
  }
}
