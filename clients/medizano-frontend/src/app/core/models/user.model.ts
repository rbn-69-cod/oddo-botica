export interface User {
  id: number;
  username: string;
  email: string;
  fullName: string;
  role: UserRole;
  active: boolean;
}

export enum UserRole {
  ADMIN = 'ADMIN',                    // All pages
  CASHIER = 'CASHIER',                // Billing
  STOCK_MONITOR = 'STOCK_MONITOR',    // Inventory
  STOCK_KEEPER = 'STOCK_KEEPER',      // Medicines
  WAREHOUSE = 'WAREHOUSE',            // Purchasing and receiving
  CUSTOMER_SUPPORT = 'CUSTOMER_SUPPORT', // Returns
  ANALYST = 'ANALYST',                // Reports
  MANAGER = 'MANAGER'                 // Reports + Purchase History
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface AuthResponse {
  authenticated?: boolean;
  token?: string;
  type?: string;
  userId?: number;
  username?: string;
  fullName?: string;
  email?: string;
  role?: string;
  mfaRequired?: boolean;
  challengeId?: string;
  maskedEmail?: string;
  expiresIn?: number;
  attemptsRemaining?: number;
  resendsRemaining?: number;
  resendAfter?: number;
  odooUrl?: string;
  frontendUrl?: string;
}


