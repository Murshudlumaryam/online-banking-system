import { api } from "@/api/client";

export interface ScheduledPaymentResponse {
  id: string;
  sender_account_id: string;
  receiver_account_number: string;
  amount: string;
  currency: string;
  frequency: "DAILY" | "WEEKLY" | "MONTHLY";
  next_run_at: string;
  is_active: boolean;
  last_executed_at: string | null;
  last_transaction_id: string | null;
  last_failure_reason: string | null;
}

export interface CreateScheduledPaymentPayload {
  sender_account_id: string;
  receiver_account_number: string;
  amount: string;
  currency: string;
  frequency: "DAILY" | "WEEKLY" | "MONTHLY";
  start_at?: string;
}

async function unwrap<T>(promise: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await promise;
  if (error) throw { response: { data: error, status: response.status } };
  return data as T;
}

export const scheduledPaymentsService = {
  async list(): Promise<ScheduledPaymentResponse[]> {
    return unwrap(api.GET("/api/v1/scheduled-payments", {}));
  },

  async create(payload: CreateScheduledPaymentPayload): Promise<ScheduledPaymentResponse> {
    return unwrap(api.POST("/api/v1/scheduled-payments", { body: payload }));
  },

  async cancel(scheduleId: string): Promise<void> {
    await api.DELETE("/api/v1/scheduled-payments/{schedule_id}", {
      params: { path: { schedule_id: scheduleId } },
    });
  },
};
