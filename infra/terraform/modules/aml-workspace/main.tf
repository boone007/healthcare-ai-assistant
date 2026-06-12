# Azure ML Workspace module
#
# Provisions the Azure Machine Learning workspace, its required Container
# Registry, and wires up the storage account, Key Vault, and Application
# Insights instances passed in from sibling modules.

resource "azurerm_container_registry" "this" {
  name                = var.container_registry_name
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = var.container_registry_sku
  admin_enabled       = false
  tags                = var.tags
}

resource "azurerm_machine_learning_workspace" "this" {
  name                    = var.name
  resource_group_name     = var.resource_group_name
  location                = var.location
  storage_account_id      = var.storage_account_id
  key_vault_id            = var.key_vault_id
  application_insights_id = var.application_insights_id
  container_registry_id   = azurerm_container_registry.this.id

  identity {
    type = "SystemAssigned"
  }

  public_network_access_enabled = var.public_network_access_enabled

  tags = var.tags
}
