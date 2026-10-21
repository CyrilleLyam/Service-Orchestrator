import axios from 'axios'
import type { ApiFailure, Envelope, JsonObject } from '#layers/shared/app/types/api'

export class ApiError extends Error {
  constructor(public detail: ApiFailure) {
    super(detail.message)
  }
}

export function useApi() {
  const request = axios.create({
    baseURL: new URL('/api/backend', useRequestURL()).href,
    headers: useRequestHeaders(['cookie', 'authorization']),
    timeout: 15000
  })
  return async <T>(path: string, options: { method?: 'GET' | 'POST' | 'PUT' | 'PATCH', body?: JsonObject, headers?: Record<string, string> } = {}) => {
    try {
      const { data: response } = await request.request<Envelope<T>>({
        url: path,
        method: options.method ?? 'GET',
        data: options.body,
        headers: options.headers
      })
      if (response.error) throw new ApiError(response.data as ApiFailure)
      return response
    } catch (error) {
      if (error instanceof ApiError) throw error
      if (axios.isAxiosError<Envelope<ApiFailure>>(error) && error.response?.data.error) {
        throw new ApiError(error.response.data.data)
      }
      throw new Error('Unable to reach the service API. Check that the backend is running and try again.', { cause: error })
    }
  }
}

export function parseObject(text: string): JsonObject {
  let value: unknown
  try {
    value = JSON.parse(text)
  } catch (error) {
    throw new Error('Enter valid JSON before continuing.', { cause: error })
  }
  if (value === null || typeof value !== 'object' || Array.isArray(value)) throw new Error('The JSON must be an object.')
  return value as JsonObject
}
