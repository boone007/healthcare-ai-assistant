output "id" {
  description = "Resource ID of the storage account"
  value       = azurerm_storage_account.this.id
}

output "name" {
  description = "Name of the storage account"
  value       = azurerm_storage_account.this.name
}

output "primary_dfs_endpoint" {
  description = "Primary ADLS Gen2 (DFS) endpoint"
  value       = azurerm_storage_account.this.primary_dfs_endpoint
}

output "primary_access_key" {
  description = "Primary access key for the storage account"
  value       = azurerm_storage_account.this.primary_access_key
  sensitive   = true
}

output "container_names" {
  description = "Names of the provisioned data lake containers"
  value = [
    azurerm_storage_container.raw.name,
    azurerm_storage_container.curated.name,
    azurerm_storage_container.models.name,
    azurerm_storage_container.monitoring.name,
  ]
}
