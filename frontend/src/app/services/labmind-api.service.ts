import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, of, throwError, delay } from 'rxjs';

@Injectable({
  providedIn: 'root'
})
export class LabmindApiService {
  private http = inject(HttpClient);

  // Branché sur le backend FastAPI réel (lancer Angular sur http://localhost:4200 ou --port 5173)
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
        general_summary: "Sur 2 paramètre(s) analysé(s), l'hémoglobine est dans la norme du laboratoire. Élément à discuter avec votre médecin : globules blancs légèrement au-dessus de la référence.",
        parameter_explanations: [
          {
            code: 'WBC',
            status: 'grounded',
            text: "Les globules blancs participent aux défenses de l'organisme contre les infections. Votre valeur est au-dessus de la borne du laboratoire ; un échange avec votre médecin permet d'en préciser le contexte.",
            source_ids: ['ameli-prise-sang-2026']
          },
          {
            code: 'HGB',
            status: 'grounded',
            text: "L'hémoglobine transporte l'oxygène vers les tissus. Votre résultat se situe dans l'intervalle normal du laboratoire.",
            source_ids: ['ameli-prise-sang-2026']
          }
        ],
        nutrition_plan: {
          status: 'grounded',
          intro: "Une alimentation variée et équilibrée soutient le bon fonctionnement général de l'organisme (repères OMS / ANSES).",
          section_title: 'Aliments d’une assiette équilibrée',
          highlights: [
            { title: 'Amandes', subtitle: 'Oléagineux source de minéraux et fibres.', image_key: 'almonds_walnuts' },
            { title: 'Noix', subtitle: 'Apport complémentaire en minéraux et acides gras.', image_key: 'walnuts' },
            { title: 'Épinards', subtitle: 'Légumes verts riches en folates et magnésium.', image_key: 'spinach' },
            { title: 'Lentilles', subtitle: 'Légumineuses sources de minéraux et protéines végétales.', image_key: 'lentils_chickpeas' },
            { title: 'Graines de courge', subtitle: 'Graines naturellement concentrées en magnésium.', image_key: 'pumpkin_seeds' }
          ],
          daily_meal_plan: [
            { meal: 'Petit-déjeuner', example: 'Flocons d’avoine ou pain complet + fruit frais' },
            { meal: 'Déjeuner', example: 'Poisson + légumes verts + céréales complètes' },
            { meal: 'Dîner', example: 'Soupe de légumes variés + yaourt nature' }
          ],
          source_ids: ['oms-has-nutrition-suivi-2025']
        },
        guidance_sections: {
          nutrition: [
            'Composer des repas variés avec légumes, fruits frais, céréales complètes et protéines adaptées.',
            'Maintenir une hydratation régulière principalement à base d’eau tout au long de la journée.'
          ],
          physical_activity: [
            'Privilégier une activité physique douce et progressive, comme la marche régulière.',
            'Limiter les périodes prolongées en position assise par de courtes pauses actives.'
          ],
          lifestyle_prevention: [
            'Conserver des horaires de sommeil réguliers pour soutenir la récupération.',
            'Éviter le tabac et limiter la consommation d’alcool ; un accompagnement médical sans jugement aide en cas de besoin.'
          ],
          medical_followup: [
            'Consulter votre médecin traitant pour discuter de la valeur de globules blancs et de vos éventuels symptômes.',
            'Réaliser un contrôle biologique uniquement si votre médecin le recommande et respecter tout traitement prescrit.'
          ]
        },
        lifestyle_info: {
          status: 'grounded',
          text: "Une alimentation variée, une hydratation régulière, une activité physique adaptée et un sommeil suffisant soutiennent l'équilibre général (repères OMS / ANSES / HAS).",
          source_ids: ['oms-has-nutrition-suivi-2025']
        },
        consultation_questions: [
          'Mon taux de globules blancs est légèrement au-dessus de la normale. Est-il nécessaire de le contrôler ?',
          'Une infection récente ou un facteur passager peut-il expliquer cette hausse ?',
          'Faut-il réaliser d’autres examens pour mieux comprendre ce résultat ?'
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
          "Impossible de communiquer avec le backend sur http://127.0.0.1:8000. Vérifiez qu'uvicorn est démarré et ouvrez l'application depuis le frontend local (http://localhost:4200 ou http://localhost:5173)."
      };
    }
    return {
      code: 'internal_error',
      message: 'Une erreur technique est survenue lors de la communication avec le serveur.'
    };
  }
}
