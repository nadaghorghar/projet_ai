import { Component, OnInit, inject } from '@angular/core';
import { Router, RouterLink } from '@angular/router';

@Component({
  selector: 'app-erreur',
  imports: [RouterLink],
  templateUrl: './erreur.component.html',
  styleUrl: './erreur.component.css'
})
export class ErreurComponent implements OnInit {
  private router = inject(Router);
  message = "Le document n'a pas pu être lu. Vérifiez qu'il s'agit d'un PDF ou d'une image nette (PNG/JPG).";

  ngOnInit(): void {
    const state = this.router.lastSuccessfulNavigation?.extras.state as
      | { message?: string }
      | undefined;
    if (state?.message) {
      this.message = state.message;
    }
  }
}
