# Key Vault module
#
# Provisions an Azure Key Vault used to store secrets referenced by the
# AML workspace (compute identity, datastore credentials) and the Azure
# Function API (AML endpoint keys, AAD client secrets).

data "azurerm_client_config" "current" {}

resource "azurerm_key_vault" "this" {
  name                       = var.name
  resource_group_name        = var.resource_group_name
  location                   = var.location
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = var.sku_name
  soft_delete_retention_days = var.soft_delete_retention_days
  purge_protection_enabled   = var.purge_protection_enabled

  enable_rbac_authorization = true

  tags = var.tags
}

# Grant the deploying principal Key Vault Administrator so Terraform/CI can
# manage secrets. In production, scope this down to a dedicated CI service
# principal and grant least-privilege roles (e.g., Key Vault Secrets Officer)
# to application managed identities separately.
resource "azurerm_role_assignment" "deployer_admin" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Administrator"
  principal_id         = data.azurerm_client_config.current.object_id
}
