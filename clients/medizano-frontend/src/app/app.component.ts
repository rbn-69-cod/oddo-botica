import { Component, OnDestroy, OnInit } from '@angular/core';
import { Router } from '@angular/router';
import { AuthService } from './auth/auth.service';
import { UserRole } from './core/models/user.model';
import { ThemeService } from './core/services/theme.service';

@Component({
  selector: 'app-root',
  standalone: false,
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss']
})
export class AppComponent implements OnInit, OnDestroy {
  title = 'MediZano';
  isAuthenticated = false;
  isStarting = true;
  readonly UserRole = UserRole;
  private startupTimer?: ReturnType<typeof setTimeout>;

  constructor(
    public authService: AuthService,
    private router: Router,
    private themeService: ThemeService
  ) {}

  get currentUser$() {
    return this.authService.currentUser$;
  }

  ngOnInit(): void {
    // Initialize theme service (detects system preference)
    this.themeService.watchSystemTheme();
    
    this.authService.currentUser$.subscribe(user => {
      this.isAuthenticated = !!user;
    });

    this.startupTimer = setTimeout(() => {
      this.isStarting = false;
    }, 1800);
  }

  ngOnDestroy(): void {
    if (this.startupTimer) {
      clearTimeout(this.startupTimer);
    }
  }

  logout(): void {
    this.authService.logout();
    this.router.navigate(['/auth/login']);
  }
}
