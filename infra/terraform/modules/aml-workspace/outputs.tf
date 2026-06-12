output "id" {
  description = "Resource ID of the Azure ML workspace"
  value       = azurerm_machine_learning_workspace.this.id
}

output "name" {
  description = "Name of the Azure ML workspace"
  value       = azurerm_machine_learning_workspace.this.name
}

output "principal_id" {
  description = "Object ID of the workspace's system-assigned managed identity"
  value       = azurerm_machine_learning_workspace.this.identity[0].principal_id
}

output "container_registry_id" {
  description = "Resource ID of the Azure Container Registry backing the workspace"
  value       = azurerm_container_registry.this.id
}
