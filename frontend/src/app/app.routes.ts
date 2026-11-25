import { Routes } from '@angular/router';
import { AccueilComponent } from './pages/accueil/accueil.component';
import { AttenteComponent } from './pages/attente/attente.component';
import { VerificationComponent } from './pages/verification/verification.component';
import { ResultatsComponent } from './pages/resultats/resultats.component';
import { ErreurComponent } from './pages/erreur/erreur.component';
import { TelechargerComponent } from './pages/telecharger/telecharger.component';

export const routes: Routes = [
  { path: '', component: AccueilComponent },
  { path: 'depot', redirectTo: '', pathMatch: 'full' },
  { path: 'attente/:id', component: AttenteComponent },
  { path: 'verification/:id', component: VerificationComponent },
  { path: 'resultats/:id', component: ResultatsComponent },
  { path: 'erreur', component: ErreurComponent },
  { path: 'telecharger', component: TelechargerComponent },
  { path: '**', redirectTo: '' }
];
