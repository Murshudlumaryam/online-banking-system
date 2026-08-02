import { api } from "@/api/client";
import type { CustomerProfile, DashboardResponse } from "@/types/api";

export interface UpdateProfilePayload {
  phone_number?: string;
  address?: string;
}

async function unwrap<T>(promise: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await promise;
  if (error) throw { response: { data: error, status: response.status } };
  return data as T;
}

export const customersService = {
  async getMyProfile(): Promise<CustomerProfile> {
    return unwrap(api.GET("/api/v1/customers/me", {}));
  },

  async updateMyProfile(payload: UpdateProfilePayload): Promise<CustomerProfile> {
    return unwrap(api.PATCH("/api/v1/customers/me", { body: payload }));
  },

  async getDashboard(): Promise<DashboardResponse> {
    return unwrap(api.GET("/api/v1/customers/me/dashboard", {}));
  },
};
