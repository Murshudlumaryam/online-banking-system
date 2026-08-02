import { api } from "@/api/client";
import type { BeneficiaryResponse } from "@/types/api";

export interface CreateBeneficiaryPayload {
  beneficiary_account_number: string;
  beneficiary_name: string;
  nickname?: string;
}

export interface UpdateBeneficiaryPayload {
  beneficiary_name?: string;
  nickname?: string;
}

async function unwrap<T>(promise: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await promise;
  if (error) throw { response: { data: error, status: response.status } };
  return data as T;
}

export const beneficiariesService = {
  async list(): Promise<BeneficiaryResponse[]> {
    return unwrap(api.GET("/api/v1/beneficiaries", {}));
  },

  async create(payload: CreateBeneficiaryPayload): Promise<BeneficiaryResponse> {
    return unwrap(api.POST("/api/v1/beneficiaries", { body: payload }));
  },

  async update(id: string, payload: UpdateBeneficiaryPayload): Promise<BeneficiaryResponse> {
    return unwrap(
      api.PATCH("/api/v1/beneficiaries/{beneficiary_id}", {
        params: { path: { beneficiary_id: id } },
        body: payload,
      }),
    );
  },

  async remove(id: string): Promise<void> {
    await api.DELETE("/api/v1/beneficiaries/{beneficiary_id}", { params: { path: { beneficiary_id: id } } });
  },
};
