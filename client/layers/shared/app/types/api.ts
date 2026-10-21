export type JsonObject = Record<string, unknown>
export interface PageMeta { page: number, pageSize: number, total: number, totalPages: number }
export interface Envelope<T> { error: boolean, data: T, pagination: PageMeta | null }
export interface FieldError { path: string, code: string, message: string, ruleId?: string | null }
export interface ApiFailure { code: string, message: string, errors: FieldError[], requestId?: string | null }
export interface VersionSummary { version: number, status: string, createdAt: string, updatedAt: string, publishedAt: string | null }
export interface Version extends VersionSummary { serviceCode: string, definition: JsonObject }
export interface ServiceSummary { code: string, name: string, description: string, currentVersion: number | null, createdAt: string }
export interface Service { code: string, name: string, description: string, published: Version | null, versions: VersionSummary[] }
export interface Fees { currency: string | null, total: number, items: { code: string, amount: number, label: string | Record<string, string> | null, quantity: number | null, unitAmount: number | null }[] }
export interface Validation { serviceCode: string, version: number, valid: boolean, errors: FieldError[] }
export interface Quote { serviceCode: string, version: number, fees: Fees }
export interface Application { id: string, serviceCode: string, serviceVersion: number, status: string, data: JsonObject, fees: Fees | null, createdAt: string, updatedAt: string, submittedAt: string | null }
export interface ApplicationDetail extends Application { events: { id: number | null, type: string, metadata: JsonObject, createdAt: string }[] }
