import { Component, OnInit } from '@angular/core';
import { FormBuilder, FormGroup, Validators } from '@angular/forms';
import { UserService, UserResponse, ChangePasswordRequest } from '../../core/services/user.service';
import { DialogService } from '../../core/services/dialog.service';
import { formatDateTime } from '../../core/utils/date-time.util';

@Component({
  selector: 'app-user-management',
  standalone: false,
  templateUrl: './user-management.component.html',
  styleUrls: ['./user-management.component.scss']
})
export class UserManagementComponent implements OnInit {
  users: UserResponse[] = [];
  filteredUsers: UserResponse[] = [];
  isLoading = false;
  searchTerm = '';
  selectedRole: string = 'ALL';
  
  // Password change modal
  showPasswordModal = false;
  selectedUser: UserResponse | null = null;
  passwordForm: FormGroup;
  isChangingPassword = false;
  showNewPassword = false;
  showConfirmPassword = false;
  
  uniqueRoles: string[] = [];

  constructor(
    private userService: UserService,
    private dialogService: DialogService,
    private fb: FormBuilder
  ) {
    this.passwordForm = this.fb.group({
      newPassword: ['', [Validators.required, Validators.minLength(8), Validators.pattern(/^(?=.*[A-Za-z])(?=.*\d).+$/)]],
      confirmPassword: ['', [Validators.required]]
    }, { validators: this.passwordMatchValidator });
  }

  ngOnInit(): void {
    this.loadUsers();
  }

  loadUsers(): void {
    this.isLoading = true;
    this.userService.getAllUsers().subscribe({
      next: (users) => {
        this.users = users;
        this.filteredUsers = users;
        this.extractUniqueRoles();
        this.isLoading = false;
      },
      error: (error) => {
        console.error('Error loading users:', error);
        this.dialogService.error('Error al cargar los usuarios: ' + (error.message || 'Error desconocido'));
        this.isLoading = false;
      }
    });
  }

  extractUniqueRoles(): void {
    this.uniqueRoles = [...new Set(this.users.map(user => user.role))].sort();
  }

  filterUsers(): void {
    this.filteredUsers = this.users.filter(user => {
      const matchesSearch = !this.searchTerm || 
        user.username.toLowerCase().includes(this.searchTerm.toLowerCase()) ||
        user.fullName.toLowerCase().includes(this.searchTerm.toLowerCase()) ||
        user.email.toLowerCase().includes(this.searchTerm.toLowerCase());
      
      const matchesRole = this.selectedRole === 'ALL' || user.role === this.selectedRole;
      
      return matchesSearch && matchesRole;
    });
  }

  openPasswordModal(user: UserResponse): void {
    this.selectedUser = user;
    this.passwordForm.reset();
    this.showPasswordModal = true;
  }

  closePasswordModal(): void {
    this.showPasswordModal = false;
    this.selectedUser = null;
    this.passwordForm.reset();
    this.showNewPassword = false;
    this.showConfirmPassword = false;
  }

  toggleNewPasswordVisibility(): void {
    this.showNewPassword = !this.showNewPassword;
  }

  toggleConfirmPasswordVisibility(): void {
    this.showConfirmPassword = !this.showConfirmPassword;
  }

  changePassword(): void {
    if (this.passwordForm.invalid || !this.selectedUser) {
      return;
    }

    this.isChangingPassword = true;
    const request: ChangePasswordRequest = {
      newPassword: this.passwordForm.value.newPassword
    };

    this.userService.changeUserPassword(this.selectedUser.id, request).subscribe({
      next: () => {
        this.dialogService.success(`Contraseña actualizada para ${this.selectedUser?.username}`);
        this.closePasswordModal();
        this.isChangingPassword = false;
      },
      error: (error) => {
        console.error('Error changing password:', error);
        this.dialogService.error('Error al cambiar la contraseña: ' + (error.message || 'Error desconocido'));
        this.isChangingPassword = false;
      }
    });
  }

  toggleUserStatus(user: UserResponse): void {
    const action = user.active ? 'desactivar' : 'activar';
    this.dialogService.confirm(
      `¿Deseas ${action} al usuario "${user.username}"?`,
      `Confirmar acción`
    ).then((confirmed) => {
      if (confirmed) {
        this.userService.updateUserStatus(user.id, !user.active).subscribe({
          next: () => {
            this.dialogService.success(`El usuario ${user.username} se actualizó correctamente`);
            this.loadUsers();
          },
          error: (error) => {
            console.error('Error updating user status:', error);
            this.dialogService.error('Error al actualizar el estado: ' + (error.message || 'Error desconocido'));
          }
        });
      }
    });
  }

  passwordMatchValidator(form: FormGroup) {
    const password = form.get('newPassword');
    const confirmPassword = form.get('confirmPassword');
    
    if (password && confirmPassword && password.value !== confirmPassword.value) {
      confirmPassword.setErrors({ passwordMismatch: true });
      return { passwordMismatch: true };
    }
    
    if (confirmPassword && confirmPassword.hasError('passwordMismatch')) {
      confirmPassword.setErrors(null);
    }
    
    return null;
  }

  getRoleBadgeClass(role: string): string {
    const roleClasses: { [key: string]: string } = {
      'ADMIN': 'badge-admin',
      'CASHIER': 'badge-cashier',
      'STOCK_MONITOR': 'badge-stock-monitor',
      'STOCK_KEEPER': 'badge-stock-keeper',
      'CUSTOMER_SUPPORT': 'badge-customer-support',
      'ANALYST': 'badge-analyst',
      'MANAGER': 'badge-manager'
    };
    return roleClasses[role] || 'badge-default';
  }

  getRoleLabel(role: string): string {
    const labels: Record<string, string> = {
      ADMIN: 'Administrador', CASHIER: 'Cajero', STOCK_MONITOR: 'Supervisor de inventario',
      STOCK_KEEPER: 'Encargado de almacén', CUSTOMER_SUPPORT: 'Atención al cliente',
      ANALYST: 'Analista', MANAGER: 'Gerente'
    };
    return labels[role] || role;
  }

  formatDate(dateString: string): string {
    return formatDateTime(dateString);
  }

  get newPassword() {
    return this.passwordForm.get('newPassword');
  }

  get confirmPassword() {
    return this.passwordForm.get('confirmPassword');
  }
}
