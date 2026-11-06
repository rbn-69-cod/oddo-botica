import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';

export interface UserResponse {
  id: number;
  username: string;
  email: string;
  fullName: string;
  role: string;
  active: boolean;
  share?: boolean;
  accountType?: string;
  createdAt: string;
  updatedAt: string;
}

export interface ChangePasswordRequest {
  newPassword: string;
}

export interface UpdateUserRequest {
  username: string;
  fullName: string;
  email: string;
  role: string;
}

export interface CreateUserRequest extends UpdateUserRequest {
  password: string;
}

@Injectable({
  providedIn: 'root'
})
export class UserService {
  constructor(private apiService: ApiService) {}

  getAllUsers(): Observable<UserResponse[]> {
    return this.apiService.get<UserResponse[]>('/admin/users');
  }

  createUser(request: CreateUserRequest): Observable<UserResponse> {
    return this.apiService.post<UserResponse>('/admin/users', request);
  }

  getUserById(userId: number): Observable<UserResponse> {
    return this.apiService.get<UserResponse>(`/admin/users/${userId}`);
  }

  changeUserPassword(userId: number, request: ChangePasswordRequest): Observable<UserResponse> {
    return this.apiService.put<UserResponse>(`/admin/users/${userId}/password`, request);
  }

  updateUser(userId: number, request: UpdateUserRequest): Observable<UserResponse> {
    return this.apiService.put<UserResponse>(`/admin/users/${userId}/profile`, request);
  }

  updateUserStatus(userId: number, active: boolean): Observable<UserResponse> {
    return this.apiService.put<UserResponse>(`/admin/users/${userId}/status?active=${active}`, {});
  }

  deleteUser(userId: number): Observable<void> {
    return this.apiService.delete<void>(`/admin/users/${userId}/delete`);
  }
}





