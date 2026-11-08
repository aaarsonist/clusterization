// Типы данных REST API сервера бизнес-логики

export type Role = 'маркетолог' | 'администратор';
export type AlgorithmId = 'kmeans' | 'agglomerative' | 'dbscan';
export type SegmentCode = 'vip' | 'churn' | 'newbie' | 'bargain' | 'regular' | 'noise';
export type RunStatus = 'черновик' | 'расчет' | 'рассчитан' | 'ошибка' | 'утвержден' | 'архивный';
export type Money = string | number;

export interface AuthUser { id: number; username: string; role: Role }

export interface UserItem {
  id: number; username: string; role: Role; is_active: boolean; created_at: string; last_login_at: string | null;
}

export interface ClusterBrief {
  id: number; cluster_no: number; segment_code: SegmentCode; cluster_label: string; description: string;
  silhouette_score: number | null; r_center: number; f_center: number; m_center: number;
  client_count: number; size_percent: number;
}

export interface Summary {
  total_clients: number; total_transactions: number; cancelled_transactions: number;
  total_revenue: Money; total_discount: Money; avg_check: Money; active_loyalty_rules: number;
  model_algorithm: AlgorithmId | null; model_approved_at: string | null; clusters: ClusterBrief[];
}

export interface Health { status: string; database: string; ai_service: string; version: string; timestamp: string }

export interface ClientListItem {
  id: number; external_code: string; full_name: string; phone: string; last_purchase_date: string | null;
  frequency: number; total_spent: Money; cluster_id: number | null; cluster_label: string | null;
  segment_code: SegmentCode | null;
}

export interface ClientListResponse { items: ClientListItem[]; total: number; page: number; limit: number; pages: number }

export interface ClientProfile {
  id: number; external_code: string; full_name: string; phone: string; email: string; created_at: string;
  recency_days: number | null; frequency: number; monetary: Money; avg_check: Money; cancelled_count: number;
  cluster_id: number | null; cluster_label: string | null; segment_code: SegmentCode | null;
  transactions: { id: number; transaction_date: string; total_amount: Money; discount_amount: Money; status: string }[];
  rules: { id: number; rule_name: string; reward_type: string; reward_value: Money; min_check_amount: Money; days_valid: number; source: string }[];
}

export interface FeatureStats {
  clients: number; active_clients: number; recency_mean: number; recency_median: number;
  frequency_mean: number; frequency_median: number; monetary_mean: number; monetary_median: number;
}

export interface ModelClusterProfile {
  cluster_no: number; segment_code: SegmentCode; cluster_label: string; description: string; client_count: number;
  size_percent: number; silhouette: number | null; r_center: number; f_center: number; m_center: number;
}

export interface ModelSummary {
  algorithm_id: AlgorithmId; name: string; silhouette_score: number; davies_bouldin_score: number;
  cluster_count: number; noise_percent: number; score: number; is_winner: boolean;
  business_suitability: string; suitability_badge: string; clusters: ModelClusterProfile[];
}

export interface Winner {
  algorithm_id: AlgorithmId; model_name: string; verdict: string; justification: string; recommendation: string;
  low_quality: boolean; quality_threshold: number;
}

export interface XaiData {
  elbow_curve: { k: number; inertia: number; silhouette: number }[];
  optimal_k: number;
  knn_distances: { index: number; distance: number }[];
  selected_eps: number; min_samples: number;
  dendrogram: { icoord: number[][]; dcoord: number[][]; color_list: string[]; ivl: string[]; cut_threshold: number };
  explained_variance_ratio: number[];
  winner: Winner;
}

export interface RunInfo {
  id: number; status: RunStatus; days_period: number; reference_date: string; target_k: number | null;
  algorithm: AlgorithmId | null; error_message: string | null; created_at: string; completed_at: string | null;
  approved_at: string | null; created_by: string | null;
}

export interface RunDetail extends RunInfo {
  features: FeatureStats;
  metrics: { n_samples: number; duration_ms: number; models: ModelSummary[] } | null;
  xai: XaiData | null;
}

export interface ScatterPoint {
  client_id: number; client_name: string; cluster_no: number; cluster_label: string; pca_x: number; pca_y: number;
  recency_days: number; frequency: number; monetary: number;
}

export interface PointsResponse { algorithm: AlgorithmId; total: number; shown: number; points: ScatterPoint[] }

export interface CurrentSegmentation {
  is_initialized: boolean; run: RunInfo | null; silhouette_score: number | null; davies_bouldin_score: number | null;
  clusters: ClusterBrief[]; total_clients: number; assigned_clients: number; latest_run: RunInfo | null;
}

export interface SnapshotInfo { id: number; kind: 'T0' | 'T1'; reference_date: string; created_at: string; clients: number }

export interface MatrixSegment { cluster_id: number; cluster_label: string; segment_code: SegmentCode }

export interface MarketingAlert {
  id: string; type: 'critical' | 'success' | 'warning' | 'info'; title: string; message: string;
  action_label: string; impact: string; target_cluster_id: number | null;
}

export interface MigrationClient {
  client_id: number; external_code: string; full_name: string; phone: string; old_cluster_id: number; old_segment: string;
  new_cluster_id: number; new_segment: string; direction: 'positive' | 'negative' | 'neutral';
}

export interface MigrationDashboard {
  state: 'ready' | 'need_baseline' | 'need_second_snapshot'; message: string; snapshots: SnapshotInfo[];
  from_snapshot: SnapshotInfo | null; to_snapshot: SnapshotInfo | null;
  summary: { total_clients_compared: number; retained: number; total_migrated: number; retention_rate: number;
             churn_risk_count: number; upgrade_count: number; downgrade_count: number } | null;
  matrix: { segments: MatrixSegment[]; matrix: number[][]; total_from: number[]; total_to: number[] } | null;
  alerts: MarketingAlert[]; clients_sample: MigrationClient[];
}

export interface DrillDownResponse {
  from_cluster: MatrixSegment; to_cluster: MatrixSegment; total_clients: number; total_turnover: Money;
  total_financial_impact: Money;
  clients: { client_id: number; external_code: string; full_name: string; phone: string; recency_days: number;
             frequency: number; monetary: Money; financial_impact: Money; impact_type: 'loss' | 'gain' | 'neutral' }[];
}

export type RewardType = 'скидка' | 'баллы' | 'кешбэк';

export interface LoyaltyRule {
  id: number; cluster_id: number | null; cluster_label: string; segment_code: SegmentCode | null; rule_name: string;
  reward_type: RewardType; reward_value: Money; min_check_amount: Money; days_valid: number; is_active: boolean;
  audience_count: number; created_by: string | null; created_at: string; updated_at: string;
}

export interface RulePayload {
  cluster_id: number | null; rule_name: string; reward_type: RewardType; reward_value: number;
  min_check_amount: number; days_valid: number; is_active: boolean;
}

export interface AudienceResponse {
  rule_id: number; rule_name: string; cluster_label: string; total_count: number; excluded_count: number;
  clients: { client_id: number; external_code: string; full_name: string; phone: string; cluster_label: string;
             total_spent: Money; is_custom_included: boolean }[];
}

export interface DiscountResponse {
  client_id: number; client_name: string; external_code: string; cluster_label: string; applied_rule_id: number | null;
  applied_rule_name: string | null; reward_type: RewardType | null; reward_value: Money | null; original_amount: Money;
  discount_amount: Money; bonus_amount: Money; final_amount: Money; benefit_description: string;
}

export interface SyncStatus {
  source_name: string; status: string; total_transactions: number; total_clients: number;
  last_transaction_date: string | null; last_sync_at: string | null;
}

export interface AuditItem {
  id: number; event_time: string; username: string | null; action: string; object_type: string | null;
  object_id: string | null; success: boolean; ip_address: string | null; details: Record<string, unknown>;
}

export interface BackupItem { file_name: string; created_at: string; kind: string; size_bytes: number; sha256: string; created_by: string | null }

export interface BackupOverview {
  settings: { enabled: boolean; run_hour: number; retention_count: number; updated_at: string };
  backups: BackupItem[]; free_space_bytes: number;
}
