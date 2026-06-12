output "resource_group_name" {
  description = "Name of the dev resource group"
  value       = module.resource_group.name
}

output "storage_account_name" {
  description = "Name of the dev storage account (data lake)"
  value       = module.storage_account.name
}

output "key_vault_uri" {
  description = "URI of the dev Key Vault"
  value       = module.key_vault.vault_uri
}

output "aml_workspace_name" {
  description = "Name of the dev Azure ML workspace"
  value       = module.aml_workspace.name
}

output "aml_compute_cluster_name" {
  description = "Name of the dev AML compute cluster"
  value       = module.aml_compute_cluster.name
}

output "app_insights_connection_string" {
  description = "Connection string for the dev Application Insights instance"
  value       = module.app_insights.connection_string
  sensitive   = true
}

output "vnet_id" {
  description = "Resource ID of the dev virtual network"
  value       = module.networking.vnet_id
}
