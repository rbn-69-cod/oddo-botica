export type BscPerspective = 'financial' | 'customer' | 'operations' | 'control';
export type BscStatus = 'on_track' | 'warning' | 'critical' | 'no_data';

export interface BscIndicator {
  code: string;
  perspective: BscPerspective;
  objective: string;
  name: string;
  unit: 'currency' | 'number' | 'percent' | 'days';
  direction: 'up' | 'down';
  target: number;
  actual: number | null;
  achievement: number | null;
  status: BscStatus;
  source: string;
  configured: boolean;
}

export interface BscReportResponse {
  startDate: string;
  endDate: string;
  generatedAt: string;
  indicators: BscIndicator[];
  summary: { averageAchievement: number | null; onTrack: number; warning: number; critical: number; noData: number; };
}
