PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS outbox_changes (
  id TEXT PRIMARY KEY,
  company_id TEXT NOT NULL,
  model TEXT NOT NULL,
  object_id TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS companies (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  logo_path TEXT,
  email_from_name TEXT,
  email_from_address TEXT,
  address1 TEXT, address2 TEXT, city TEXT, state TEXT, zip_code TEXT,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 0,
  deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS employee_profiles (
  id TEXT PRIMARY KEY,
  company_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  display_name TEXT,
  username_public TEXT NOT NULL,
  role TEXT NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 1,
  hired_at TEXT,
  terminated_at TEXT,
  hourly_rate REAL,
  can_view_company_financials INTEGER NOT NULL DEFAULT 0,
  can_approve_time INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 0,
  deleted_at TEXT,
  UNIQUE(company_id, username_public),
  UNIQUE(company_id, user_id),
  FOREIGN KEY(company_id) REFERENCES companies(id)
);

CREATE TABLE IF NOT EXISTS clients (
  id TEXT PRIMARY KEY,
  company_id TEXT NOT NULL,
  first_name TEXT, last_name TEXT, company_name TEXT,
  email TEXT,
  internal_note TEXT,
  address1 TEXT, address2 TEXT, city TEXT, state TEXT, zip_code TEXT,
  credit_cents INTEGER NOT NULL DEFAULT 0,
  outstanding_cents INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 0,
  deleted_at TEXT,
  FOREIGN KEY(company_id) REFERENCES companies(id)
);

CREATE INDEX IF NOT EXISTS idx_clients_company_sort ON clients(company_id, company_name, last_name, first_name);

CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY,
  company_id TEXT NOT NULL,
  client_id TEXT,
  project_number TEXT,
  name TEXT NOT NULL,
  description TEXT,
  date_received TEXT,
  due_date TEXT,
  billing_type TEXT NOT NULL,
  flat_fee_cents INTEGER NOT NULL DEFAULT 0,
  hourly_rate_cents INTEGER NOT NULL DEFAULT 0,
  estimated_minutes INTEGER NOT NULL DEFAULT 0,
  assigned_to_employee_id TEXT,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 0,
  deleted_at TEXT,
  FOREIGN KEY(company_id) REFERENCES companies(id),
  FOREIGN KEY(client_id) REFERENCES clients(id),
  FOREIGN KEY(assigned_to_employee_id) REFERENCES employee_profiles(id)
);

CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY,
  company_id TEXT NOT NULL,
  doc_type TEXT NOT NULL,
  client_id TEXT,
  created_by_employee_id TEXT,
  number TEXT,
  title TEXT,
  description TEXT,
  issue_date TEXT,
  due_date TEXT,
  valid_until TEXT,
  status TEXT NOT NULL,
  subtotal_cents INTEGER NOT NULL DEFAULT 0,
  tax_cents INTEGER NOT NULL DEFAULT 0,
  total_cents INTEGER NOT NULL DEFAULT 0,
  amount_paid_cents INTEGER NOT NULL DEFAULT 0,
  balance_due_cents INTEGER NOT NULL DEFAULT 0,
  notes TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 0,
  deleted_at TEXT,
  FOREIGN KEY(company_id) REFERENCES companies(id),
  FOREIGN KEY(client_id) REFERENCES clients(id),
  FOREIGN KEY(created_by_employee_id) REFERENCES employee_profiles(id)
);

CREATE INDEX IF NOT EXISTS idx_documents_company_type_status ON documents(company_id, doc_type, status);

CREATE TABLE IF NOT EXISTS document_line_items (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0,
  catalog_item_id TEXT,
  name TEXT NOT NULL,
  description TEXT,
  qty REAL NOT NULL DEFAULT 1,
  unit_price_cents INTEGER NOT NULL DEFAULT 0,
  line_subtotal_cents INTEGER NOT NULL DEFAULT 0,
  tax_cents INTEGER NOT NULL DEFAULT 0,
  line_total_cents INTEGER NOT NULL DEFAULT 0,
  is_taxable INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 0,
  deleted_at TEXT,
  FOREIGN KEY(document_id) REFERENCES documents(id)
);

CREATE TABLE IF NOT EXISTS time_entries (
  id TEXT PRIMARY KEY,
  company_id TEXT NOT NULL,
  employee_id TEXT,
  client_id TEXT,
  project_id TEXT,
  started_at TEXT,
  ended_at TEXT,
  duration_minutes INTEGER NOT NULL DEFAULT 0,
  billable INTEGER NOT NULL DEFAULT 1,
  note TEXT,
  status TEXT NOT NULL,
  approved_by_employee_id TEXT,
  approved_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 0,
  deleted_at TEXT,
  FOREIGN KEY(company_id) REFERENCES companies(id),
  FOREIGN KEY(employee_id) REFERENCES employee_profiles(id),
  FOREIGN KEY(client_id) REFERENCES clients(id),
  FOREIGN KEY(project_id) REFERENCES projects(id)
);
