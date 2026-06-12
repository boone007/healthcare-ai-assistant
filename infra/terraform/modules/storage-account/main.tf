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
  is_hns_enabled           = var.is_hns_enabled # Enables ADLS Gen2 hierarchical namespace

  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false

  tags = var.tags
}

# Data lake containers / filesystems for each pipeline zone. Skipped for
# storage accounts dedicated to an AML workspace's default storage (AML
# manages its own containers in that account).
resource "azurerm_storage_container" "raw" {
  count                 = var.create_data_lake_containers ? 1 : 0
  name                  = "raw"
  storage_account_name  = azurerm_storage_account.this.name
  container_access_type = "private"
}

resource "azurerm_storage_container" "curated" {
  count                 = var.create_data_lake_containers ? 1 : 0
  name                  = "curated"
  storage_account_name  = azurerm_storage_account.this.name
  container_access_type = "private"
}

resource "azurerm_storage_container" "models" {
  count                 = var.create_data_lake_containers ? 1 : 0
  name                  = "models"
  storage_account_name  = azurerm_storage_account.this.name
  container_access_type = "private"
}

resource "azurerm_storage_container" "monitoring" {
  count                 = var.create_data_lake_containers ? 1 : 0
  name                  = "monitoring"
  storage_account_name  = azurerm_storage_account.this.name
  container_access_type = "private"
}
