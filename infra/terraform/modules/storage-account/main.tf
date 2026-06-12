# Storage Account module
#
# Provisions an ADLS Gen2-enabled storage account (hierarchical namespace)
# used as the data lake for the data pipeline (raw / curated / models zones)
# and as the default datastore for the Azure ML workspace.

resource "azurerm_storage_account" "this" {
  name                     = var.name
  resource_group_name      = var.resource_group_name
  location                 = var.location
  account_tier             = var.account_tier
  account_replication_type = var.replication_type
  account_kind             = "StorageV2"
  is_hns_enabled           = true # Enables ADLS Gen2 hierarchical namespace

  min_tls_version                = "TLS1_2"
  allow_nested_items_to_be_public = false

  tags = var.tags
}

# Data lake containers / filesystems for each pipeline zone
resource "azurerm_storage_container" "raw" {
  name                  = "raw"
  storage_account_id   = azurerm_storage_account.this.id
  container_access_type = "private"
}

resource "azurerm_storage_container" "curated" {
  name                  = "curated"
  storage_account_id   = azurerm_storage_account.this.id
  container_access_type = "private"
}

resource "azurerm_storage_container" "models" {
  name                  = "models"
  storage_account_id   = azurerm_storage_account.this.id
  container_access_type = "private"
}

resource "azurerm_storage_container" "monitoring" {
  name                  = "monitoring"
  storage_account_id   = azurerm_storage_account.this.id
  container_access_type = "private"
}
