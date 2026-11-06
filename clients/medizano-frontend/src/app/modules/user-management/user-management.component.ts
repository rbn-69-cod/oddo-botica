import { Component, OnInit } from '@angular/core';
import { FormBuilder, FormGroup, Validators } from '@angular/forms';
import { UserService, UserResponse, ChangePasswordRequest, CreateUserRequest, UpdateUserRequest } from '../../core/services/user.service';
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
  showEditModal = false;
  editForm: FormGroup;
  isSavingUser = false;
  showCreateModal = false;
  createForm: FormGroup;
  isCreatingUser = false;
  showCreatePassword = false;
  
  uniqueRoles: string[] = [];
  readonly editableRoles = ['ADMIN', 'MANAGER', 'CASHIER', 'WAREHOUSE', 'STOCK_KEEPER', 'CUSTOMER_SUPPORT', 'ANALYST'];

  constructor(
    private userService: UserService,
    private dialogService: DialogService,
    private fb: FormBuilder
  ) {
    this.passwordForm = this.fb.group({
      newPassword: ['', [Validators.required, Validators.minLength(8), Validators.pattern(/^(?=.*[A-Za-z])(?=.*\d).+$/)]],
      confirmPassword: ['', [Validators.required]]
    }, { validators: this.passwordMatchValidator });
    this.editForm = this.fb.group({
      username: ['', [Validators.required, Validators.minLength(3)]],
      fullName: ['', [Validators.required, Validators.minLength(3)]],
      email: ['', [Validators.email]],
      role: ['', Validators.required]
    });
    this.createForm = this.fb.group({
      username: ['', [Validators.required, Validators.minLength(3)]],
      fullName: ['', [Validators.required, Validators.minLength(3)]],
      email: ['', [Validators.email]],
      role: ['CASHIER', Validators.required],
      password: ['', [Validators.required, Validators.minLength(8), Validators.pattern(/^(?=.*[A-Za-z])(?=.*\d).+$/)]],
      confirmPassword: ['', Validators.required]
    }, { validators: this.createPasswordMatchValidator });
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

  openCreateModal(): void {
    this.createForm.reset({ role: 'CASHIER' });
    this.showCreatePassword = false;
    this.showCreateModal = true;
  }

  closeCreateModal(): void {
    if (this.isCreatingUser) return;
    this.showCreateModal = false;
    this.showCreatePassword = false;
    this.createForm.reset({ role: 'CASHIER' });
  }

  createUser(): void {
    if (this.createForm.invalid) {
      this.createForm.markAllAsTouched();
      return;
    }
    const request: CreateUserRequest = {
      username: this.createForm.value.username.trim(),
      fullName: this.createForm.value.fullName.trim(),
      email: (this.createForm.value.email || '').trim(),
      role: this.createForm.value.role,
      password: this.createForm.value.password
    };
    this.isCreatingUser = true;
    this.userService.createUser(request).subscribe({
      next: () => {
        this.isCreatingUser = false;
        this.closeCreateModal();
        this.dialogService.success('Usuario creado correctamente');
        this.loadUsers();
      },
      error: (error) => {
        this.isCreatingUser = false;
        this.dialogService.error(error.message || 'No se pudo crear el usuario');
      }
    });
  }

  deleteUser(user: UserResponse): void {
    if (user.username === 'admin') {
      this.dialogService.warning('El Administrador Maestro es una cuenta protegida y no se puede eliminar.');
      return;
    }

    this.dialogService.confirm(
      `¿Eliminar definitivamente la cuenta de "${user.fullName}"? Esta acción no se puede deshacer.`,
      'Eliminar usuario'
    ).then((confirmed) => {
      if (!confirmed) return;
      this.userService.deleteUser(user.id).subscribe({
        next: () => {
          this.dialogService.success(`Usuario ${user.username} eliminado correctamente`);
          this.loadUsers();
        },
        error: (error) => this.dialogService.error(error.message || 'No se pudo eliminar el usuario')
      });
    });
  }

  openEditModal(user: UserResponse): void {
    this.selectedUser = user;
    this.editForm.reset({
      username: user.username,
      fullName: user.fullName,
      email: user.email,
      role: user.role
    });
    this.showEditModal = true;
  }

  closeEditModal(): void {
    if (this.isSavingUser) return;
    this.showEditModal = false;
    this.selectedUser = null;
    this.editForm.reset();
  }

  saveUser(): void {
    if (!this.selectedUser || this.editForm.invalid) {
      this.editForm.markAllAsTouched();
      return;
    }
    const request: UpdateUserRequest = {
      username: this.editForm.value.username.trim(),
      fullName: this.editForm.value.fullName.trim(),
      email: (this.editForm.value.email || '').trim(),
      role: this.editForm.value.role
    };
    this.isSavingUser = true;
    this.userService.updateUser(this.selectedUser.id, request).subscribe({
      next: () => {
        this.isSavingUser = false;
        this.showEditModal = false;
        this.selectedUser = null;
        this.dialogService.success('Datos del usuario actualizados correctamente');
        this.loadUsers();
      },
      error: (error) => {
        this.isSavingUser = false;
        this.dialogService.error(error.message || 'No se pudo actualizar el usuario');
      }
    });
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
    if (user.username === 'admin') {
      this.dialogService.warning('El Administrador Maestro es una cuenta protegida y no se puede desactivar.');
      return;
    }

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

  createPasswordMatchValidator(form: FormGroup) {
    const password = form.get('password');
    const confirmation = form.get('confirmPassword');
    if (password && confirmation && password.value !== confirmation.value) {
      confirmation.setErrors({ passwordMismatch: true });
      return { passwordMismatch: true };
    }
    if (confirmation?.hasError('passwordMismatch')) confirmation.setErrors(null);
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
      STOCK_KEEPER: 'Encargado de inventario', WAREHOUSE: 'Almacén', CUSTOMER_SUPPORT: 'Atención al cliente',
      ANALYST: 'Analista', MANAGER: 'Gerente'
    };
    return labels[role] || role;
  }

  getAccountTypeLabel(accountType?: string): string {
    const labels: Record<string, string> = {
      internal: 'Interno',
      portal: 'Portal',
      technical: 'Técnico'
    };
    return labels[accountType || ''] || 'No definido';
  }

  formatDate(dateString: string): string {
    return formatDateTime(dateString);
  }

  get initials(): string {
    return (this.selectedUser?.fullName || this.selectedUser?.username || 'U')
      .split(/\s+/).slice(0, 2).map(value => value.charAt(0).toUpperCase()).join('');
  }

  get newPassword() {
    return this.passwordForm.get('newPassword');
  }

  get confirmPassword() {
    return this.passwordForm.get('confirmPassword');
  }
}
