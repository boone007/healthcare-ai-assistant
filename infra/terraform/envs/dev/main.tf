# Dev environment
#
# Wires together the resource-group, networking, storage-account,
# key-vault, app-insights, aml-workspace, and aml-compute-cluster modules
# to provision the full dev environment for the Healthcare AI Assistant.

module "resource_group" {
  source = "../../modules/resource-group"

  name     = "rg-hcai-${var.environment}"
  location = var.location
  tags     = var.tags
}

module "networking" {
  source = "../../modules/networking"

  vnet_name           = "vnet-hcai-${var.environment}"
  resource_group_name = module.resource_group.name
  location            = module.resource_group.location
  address_space       = "10.20.0.0/16"
  aml_subnet_prefix   = "10.20.1.0/24"
  app_subnet_prefix   = "10.20.2.0/24"
  tags                = var.tags
}

module "storage_account" {
  source = "../../modules/storage-account"

  name                 = "sthcai${var.environment}001"
  resource_group_name  = module.resource_group.name
  location             = module.resource_group.location
  account_tier         = "Standard"
  replication_type     = "LRS"
  tags                 = var.tags
}

# Dedicated storage account for the AML workspace's default/system storage.
# The AML control plane rejects ADLS Gen2 (HNS-enabled) storage accounts as
# the workspace's default storage, so this is separate from the
# sthcai{env}001 data lake used by the data pipeline.
module "aml_storage_account" {
  source = "../../modules/storage-account"

  name                         = "stmlhcai${var.environment}001"
  resource_group_name          = module.resource_group.name
  location                     = module.resource_group.location
  account_tier                 = "Standard"
  replication_type             = "LRS"
  is_hns_enabled               = false
  create_data_lake_containers  = false
  tags                         = var.tags
}

module "key_vault" {
  source = "../../modules/key-vault"

  name                       = "kv-hcai-${var.environment}"
  resource_group_name       = module.resource_group.name
  location                   = module.resource_group.location
  sku_name                   = "standard"
  soft_delete_retention_days = 7
  purge_protection_enabled   = false
  tags                       = var.tags
}

module "app_insights" {
  source = "../../modules/app-insights"

  name                = "appi-hcai-${var.environment}"
  resource_group_name = module.resource_group.name
  location            = module.resource_group.location
  log_retention_days  = 30
  tags                = var.tags
}

module "aml_workspace" {
  source = "../../modules/aml-workspace"

  name                     = "mlw-hcai-${var.environment}"
  resource_group_name      = module.resource_group.name
  location                 = module.resource_group.location
  storage_account_id       = module.aml_storage_account.id
  key_vault_id             = module.key_vault.id
  application_insights_id  = module.app_insights.id
  container_registry_name  = "acrhcai${var.environment}001"
  container_registry_sku   = "Basic"

  # Dev allows public network access for ease of iteration.
  public_network_access_enabled = true

  tags = var.tags
}

module "aml_compute_cluster" {
  source = "../../modules/aml-compute-cluster"

  name              = "cpu-cluster-${var.environment}"
  location          = module.resource_group.location
  aml_workspace_id  = module.aml_workspace.id
  vm_size           = var.compute_vm_size
  vm_priority       = "Dedicated"
  min_node_count    = var.compute_min_nodes
  max_node_count    = var.compute_max_nodes
  scale_down_idle_duration = "PT30M"

  tags = var.tags
}
