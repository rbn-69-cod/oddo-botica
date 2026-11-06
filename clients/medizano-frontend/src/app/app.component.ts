import { Component, OnDestroy, OnInit } from '@angular/core';
import { Router } from '@angular/router';
import { AuthService } from './auth/auth.service';
import { UserRole } from './core/models/user.model';
import { ThemeService } from './core/services/theme.service';
import { finalize } from 'rxjs/operators';

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
  private lastSsoCheck = 0;
  private readonly onWindowFocus = () => this.synchronizeSession(false);
  private readonly onVisibilityChange = () => {
    if (document.visibilityState === 'visible') this.synchronizeSession(false);
  };

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

    this.synchronizeSession(true);
    window.addEventListener('focus', this.onWindowFocus);
    document.addEventListener('visibilitychange', this.onVisibilityChange);

    // Fallback so a network interruption cannot leave the splash visible.
    this.startupTimer = setTimeout(() => this.isStarting = false, 5000);
  }

  ngOnDestroy(): void {
    if (this.startupTimer) {
      clearTimeout(this.startupTimer);
    }
    window.removeEventListener('focus', this.onWindowFocus);
    document.removeEventListener('visibilitychange', this.onVisibilityChange);
  }

  private synchronizeSession(initial: boolean): void {
    const now = Date.now();
    if (!initial && now - this.lastSsoCheck < 1000) return;
    this.lastSsoCheck = now;

    this.authService.restoreSsoSession().pipe(
      finalize(() => {
        if (initial) this.isStarting = false;
      })
    ).subscribe(restored => {
      if (restored) {
        if (this.router.url.startsWith('/auth/') || this.router.url === '/') {
          this.router.navigate(['/dashboard']);
        }
        return;
      }

      if (!initial && !this.router.url.startsWith('/auth/')) {
        this.router.navigate(['/auth/login']);
      }
    });
  }

  logout(): void {
    this.authService.logout();
    this.router.navigate(['/auth/login']);
  }
}
