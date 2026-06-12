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
  description = "Names of the provisioned data lake containers (empty if create_data_lake_containers is false)"
  value = var.create_data_lake_containers ? [
    azurerm_storage_container.raw[0].name,
    azurerm_storage_container.curated[0].name,
    azurerm_storage_container.models[0].name,
    azurerm_storage_container.monitoring[0].name,
  ] : []
}
